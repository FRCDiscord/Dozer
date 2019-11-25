"""Provides moderation commands for Dozer."""
import asyncio
import re
import datetime
import time
from typing import Union
from logging import getLogger

import discord
from discord.ext.commands import BadArgument, has_permissions, RoleConverter

from ._utils import *
from .. import db


class SafeRoleConverter(RoleConverter):
    """Allows for @everyone to be specified without pinging everyone"""
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            if argument.casefold() in (
                    'everyone', '@everyone', '@/everyone', '@.everyone', '@ everyone', '@\N{ZERO WIDTH SPACE}everyone'):
                return ctx.guild.default_role
            else:
                raise


class Moderation(Cog):
    """A cog to handle moderation tasks."""

    def __init__(self, bot):
        super().__init__(bot)
        self.edit_delete_config = db.ConfigCache(GuildMessageLog)
        self.links_config = db.ConfigCache(GuildMessageLinks)

    """=== Helper functions ==="""

    async def mod_log(self, actor: discord.Member, action: str, target: Union[discord.User, discord.Member], reason, orig_channel=None,
                      embed_color=discord.Color.red(), global_modlog=True):
        """Generates a modlog embed"""
        modlog_embed = discord.Embed(
            color=embed_color,
            title=f"User {action}!"

        )
        modlog_embed.add_field(name=f"{action.capitalize()} user", value=f"{target.mention} ({target} | {target.id})", inline=False)
        modlog_embed.add_field(name="Requested by", value=f"{actor.mention} ({actor} | {actor.id})", inline=False)
        modlog_embed.add_field(name="Reason", value=reason or "No reason specified", inline=False)
        modlog_embed.add_field(name="Timestamp", value=str(datetime.datetime.now()), inline=False)
        try:
            await target.send(embed=modlog_embed)
        except discord.Forbidden:
            await orig_channel.send("Failed to DM modlog to user")
        modlog_channel = await GuildModLog.get_by_guild(guild_id=actor.guild.id)
        if orig_channel is not None:
            await orig_channel.send(embed=modlog_embed)
        if len(modlog_channel) != 0:
            if global_modlog:
                channel = actor.guild.get_channel(modlog_channel[0].modlog_channel)
                if channel is not None and channel != orig_channel: # prevent duplicate embeds
                    await channel.send(embed=modlog_embed)
        else:
            if orig_channel is not None:
                await orig_channel.send("Please configure modlog channel to enable modlog functionality")

    async def perm_override(self, member, **overwrites):
        """Applies the given overrides to the given member in their guild."""
        coros = []
        for channel in member.guild.channels:
            overwrite = channel.overwrites_for(member)
            can_perm_override = channel.permissions_for(member.guild.me).manage_roles
            if can_perm_override:
                overwrite.update(**overwrites)
                coros.append(
                    channel.set_permissions(target=member, overwrite=None if overwrite.is_empty() else overwrite))
        await asyncio.gather(*coros)

    hm_regex = re.compile(r"((?P<hours>\d+)h)?((?P<minutes>\d+)m)?((?P<seconds>\d+)s)?")

    def hm_to_seconds(self, hm_str):
        """Converts an hour-minute string to seconds. For example, '1h15m' returns 4500"""
        matches = re.match(self.hm_regex, hm_str).groupdict()
        hours = int(matches.get('hours') or 0)
        minutes = int(matches.get('minutes') or 0)
        seconds = int(matches.get('seconds') or 0)
        return (hours * 3600) + (minutes * 60) + seconds

    async def punishment_timer(self, seconds, target: discord.Member, punishment, reason, actor: discord.Member, orig_channel=None,
                               global_modlog=True):
        """Asynchronous task that sleeps for a set time to unmute/undeafen a member for a set period of time."""
        if seconds == 0:
            return

        # register the timer
        ent = PunishmentTimerRecord(
            guild_id=target.guild.id,
            actor_id=actor.id,
            target_id=target.id,
            orig_channel_id=orig_channel.id if orig_channel else 0,
            type_of_punishment=punishment.type,
            reason=reason,
            target_ts=int(seconds + time.time())
        )
        await ent.update_or_add()

        await asyncio.sleep(seconds)

        user = await punishment.get_by_user(user_id=target.id, user_column_name="target_id")
        if len(user) != 0:
            await self.mod_log(actor,
                               "un" + punishment.past_participle,
                               target,
                               reason,
                               orig_channel,
                               embed_color=discord.Color.green(),
                               global_modlog=global_modlog)
            self.bot.loop.create_task(coro=punishment.finished_callback(self, target))

        if ent:
            await ent.dual_criteria_delete(data_column="guild_id", data=target.guild.id,
                                           data_column_two="target_id", data_two=target.id)

    async def _check_links_warn(self, msg, role):
        """Warns a user that they can't send links."""
        warn_msg = await msg.channel.send(f"{msg.author.mention}, you need the `{role.name}` role to post links!")
        await asyncio.sleep(3)
        await warn_msg.delete()

    async def check_links(self, msg):
        """Checks messages for the links role if necessary, then checks if the author is allowed to send links in the server"""
        if msg.guild is None or not isinstance(msg.author, discord.Member) or not msg.guild.me.guild_permissions.manage_messages:
            return
        config = await self.links_config.query_one(guild_id=msg.guild.id)
        if config is None:
            return
        role = msg.guild.get_role(config.role_id)
        if role is None:
            return
        if role not in msg.author.roles and re.search("https?://", msg.content):
            await msg.delete()
            self.bot.loop.create_task(self._check_links_warn(msg, role))
            return True
        return False

    """=== context-free backend functions ==="""

    async def _mute(self, member: discord.Member, reason: str = "No reason provided", seconds=0, actor=None, orig_channel=None):
        """Mutes a user.
        member: the member to be muted
        reason: a reason string without a time specifier
        seconds: a duration of time for the mute to be applied. If 0, then the mute is indefinite. Do not set negative durations.
        actor: the acting user who requested the mute
        orig_channel: the channel of the request origin
        """
        user = None
        results = await Mute.get_by_guild(guild_id=member.guild.id)
        for result in results:
            if result.member_id == member.id:
                user = result
                break

        if user is not None:
            return False # member already muted
        else:
            user = Mute(member_id=member.id, guild_id=member.guild.id)
            await user.update_or_add()
            await self.perm_override(member, send_messages=False, add_reactions=False)

            self.bot.loop.create_task(
                self.punishment_timer(seconds, member, Mute, reason, actor or member.guild.me, orig_channel=orig_channel))
            return True

    async def _unmute(self, member: discord.Member):
        """Unmutes a user."""
        results = await Mute.get_by_guild(guild_id=member.guild.id)
        user = None
        for result in results:
            if result.member_id == member.id:
                user = result
                break
        if user is not None:
            await user.dual_criteria_delete(data_column="member_id", data=member.id,
                                            data_column_two="guild_id", data_two=member.guild.id)
            await self.perm_override(member, send_messages=None, add_reactions=None)
            return True
        else:
            return False # member not muted

    async def _deafen(self, member: discord.Member, reason: str = "No reason provided", seconds=0, self_inflicted: bool = False, actor=None,
                      orig_channel=None):
        """Deafens a user.
        member: the member to be deafened
        reason: a reason string without a time specifier
        seconds: a duration of time for the mute to be applied. If 0, then the mute is indefinite. Do not set negative durations.
        self_inflicted: specifies if the deafen is a self-deafen
        actor: the acting user who requested the mute
        orig_channel: the channel of the request origin
        """
        results = await Deafen.get_by_guild(guild_id=member.guild.id)
        if len(results) != 0:
            for result in results:
                if result.member_id == member.id:
                    return False
        else:
            user = Deafen(member_id=member.id, guild_id=member.guild.id, self_inflicted=self_inflicted)
            await user.update_or_add()
            await self.perm_override(member, read_messages=False)

            if self_inflicted and seconds == 0:
                seconds = 30 # prevent lockout in case of bad argument
            self.bot.loop.create_task(
                self.punishment_timer(seconds, member,
                                      punishment=Deafen,
                                      reason=reason,
                                      actor=actor or member.guild.me,
                                      orig_channel=orig_channel,
                                      global_modlog=not self_inflicted))
            return True

    async def _undeafen(self, member: discord.Member, reason, ctx):
        """Undeafens a user."""
        users = await Deafen.get_by_guild(guild_id=member.guild.id)
        user = None
        for user_to_check in users:
            if user_to_check.member_id == member.id:
                user = user_to_check
                break
        if user is not None:
            await self.perm_override(member=member, read_messages=None)
            await user.dual_criteria_delete(data_column="guild_id", data=member.guild.id, data_column_two="member_id",
                                            data_two=member.id)
            await self.mod_log(actor=ctx.author, action="undeafened", target=member, reason=reason,
                               orig_channel=ctx.channel, embed_color=discord.Color.green(), global_modlog=not user.self_inflicted)
        else:
            await ctx.send("Member is not deafened!")

    """=== Event handlers ==="""

    @Cog.listener('on_ready')
    async def on_ready(self):
        """Restore punishment timers on bot startup"""
        q = await PunishmentTimerRecord.get_all()
        for r in q:
            guild = self.bot.get_guild(r.guild_id)
            actor = guild.get_member(r.actor_id)
            target = guild.get_member(r.target_id)
            orig_channel = self.bot.get_channel(r.orig_channel_id)
            punishment_type = r.type
            reason = r.reason or ""
            seconds = max(int(r.target_ts - time.time()), 0.01)
            await r.delete()
            self.bot.loop.create_task(self.punishment_timer(seconds, target, PunishmentTimerRecord.type_map[punishment_type], reason, actor,
                                                            orig_channel))
            getLogger('dozer').info(f"Restarted {PunishmentTimerRecord.type_map[punishment_type].__name__} of {target} in {guild}")

    @Cog.listener('on_member_join')
    async def on_member_join(self, member):
        """Logs that a member joined."""
        join = discord.Embed(type='rich', color=0x00FF00)
        join.set_author(name='Member Joined', icon_url=member.avatar_url_as(format='png', size=32))
        join.description = "{0.mention}\n{0} ({0.id})".format(member)
        join.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
        memberlogchannel = await GuildMemberLog.get_by_guild(guild_id=member.guild.id)
        if len(memberlogchannel) != 0:
            channel = member.guild.get_channel(memberlogchannel[0].memberlog_channel)
            await channel.send(embed=join)
        users = await Mute.get_by_guild(guild_id=member.guild.id)
        for user in users:
            if user.member_id == member.id:
                await self.perm_override(member, add_reactions=False, send_messages=False)
        users = await Deafen.get_by_guild(guild_id=member.guild.id)
        for user in users:
            if user.member_id == member.id:
                await self.perm_override(member, read_messages=False)

    @Cog.listener('on_member_remove')
    async def on_member_remove(self, member):
        """Logs that a member left."""
        leave = discord.Embed(type='rich', color=0xFF0000)
        leave.set_author(name='Member Left', icon_url=member.avatar_url_as(format='png', size=32))
        leave.description = "{0.mention}\n{0} ({0.id})".format(member)
        leave.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
        memberlogchannel = await GuildMemberLog.get_by_guild(guild_id=member.guild.id)
        if len(memberlogchannel) != 0:
            channel = member.guild.get_channel(memberlogchannel[0].memberlog_channel)
            await channel.send(embed=leave)

    @Cog.listener('on_message')
    async def on_message(self, message):
        """Check things when messages come in."""
        if message.author.bot or message.guild is None or not message.guild.me.guild_permissions.manage_roles:
            return

        #if await self.check_links(message):
        #    return
        config = await GuildNewMember.get_by_guild(guild_id=message.guild.id)
        if len(config) != 0:
            config = config[0]
            string = config.message
            content = message.content.casefold()
            if string not in content:
                return
            channel = config.channel_id
            role_id = config.role_id
            if message.channel.id != channel:
                return
            await message.author.add_roles(message.guild.get_role(role_id))

    @Cog.listener('on_message_delete')
    async def on_message_delete(self, message):
        """When a message is deleted, log it."""
        e = discord.Embed(type='rich')
        e.title = 'Message Deletion'
        e.color = 0xFF0000
        e.timestamp = datetime.datetime.utcnow()
        e.add_field(name='Author', value=message.author)
        e.add_field(name='Author pingable', value=message.author.mention)
        e.add_field(name='Channel', value=message.channel)
        if 1024 > len(message.content) > 0:
            e.add_field(name="Deleted message", value=message.content)
        elif len(message.content) != 0:
            e.add_field(name="Deleted message", value=message.content[0:1023])
            e.add_field(name="Deleted message continued", value=message.content[1024:2000])
        elif len(message.content) == 0:
            for i in message.embeds:
                e.add_field(name="Title", value=i.title)
                e.add_field(name="Description", value=i.description)
                e.add_field(name="Timestamp", value=i.timestamp)
                for x in i.fields:
                    e.add_field(name=x.name, value=x.value)
                e.add_field(name="Footer", value=i.footer)
        if message.attachments:
            e.add_field(name="Attachments", value=", ".join([i.url for i in message.attachments]))
        messagelogchannel = self.edit_delete_config.query_one(id=message.guild.id)
        if messagelogchannel is not None:
            channel = message.guild.get_channel(messagelogchannel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=e)

    @Cog.listener('on_message_edit')
    async def on_message_edit(self, before, after):
        """Logs message edits."""
        await self.check_links(after)
        if before.author.bot:
            return
        if after.edited_at is not None or before.edited_at is not None:
            # There is a reason for this. That reason is that otherwise, an infinite spam loop occurs
            e = discord.Embed(type='rich')
            e.title = 'Message Edited'
            e.color = 0xFFC400
            e.timestamp = after.edited_at
            e.add_field(name='Author', value=before.author)
            e.add_field(name='Author pingable', value=before.author.mention)
            e.add_field(name='Channel', value=before.channel)
            if 1024 > len(before.content) > 0:
                e.add_field(name="Old message", value=before.content)
            elif len(before.content) != 0:
                e.add_field(name="Old message", value=before.content[0:1023])
                e.add_field(name="Old message continued", value=before.content[1024:2000])
            elif len(before.content) == 0 and before.edited_at is not None:
                for i in before.embeds:
                    e.add_field(name="Title", value=i.title)
                    e.add_field(name="Description", value=i.description)
                    e.add_field(name="Timestamp", value=i.timestamp)
                    for x in i.fields:
                        e.add_field(name=x.name, value=x.value)
                    e.add_field(name="Footer", value=i.footer)
            if before.attachments:
                e.add_field(name="Attachments", value=", ".join([i.url for i in before.attachments]))
            if 0 < len(after.content) < 1024:
                e.add_field(name="New message", value=after.content)
            elif len(after.content) != 0:
                e.add_field(name="New message", value=after.content[0:1023])
                e.add_field(name="New message continued", value=after.content[1024:2000])
            elif len(after.content) == 0 and after.edited_at is not None:
                for i in after.embeds:
                    e.add_field(name="Title", value=i.title)
                    e.add_field(name="Description", value=i.description)
                    e.add_field(name="Timestamp", value=i.timestamp)
                    for x in i.fields:
                        e.add_field(name=x.name, value=x.value)
            if after.attachments:
                e.add_field(name="Attachments", value=", ".join([i.url for i in before.attachments]))
            messagelogchannel = self.edit_delete_config.query_one(id=before.guild.id)
            if messagelogchannel is not None:
                channel = before.guild.get_channel(messagelogchannel.messagelog_channel)
                if channel is not None:
                    await channel.send(embed=e)

    """=== Direct moderation commands ==="""

    @command()
    @has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason):
        """Sends a message to the mod log specifying the member has been warned without punishment."""
        await self.mod_log(actor=ctx.author, action="warned", target=member, orig_channel=ctx.channel, reason=reason)

    warn.example_usage = """
    `{prefix}`warn @user reason - warns a user for "reason"
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_roles=True)
    async def timeout(self, ctx, duration: float):
        """Set a timeout (no sending messages or adding reactions) on the current channel."""
        settings = await MemberRole.get_by_guild(guild_id=ctx.guild.id)
        if len(settings) == 0:
            settings = MemberRole(guild_id=ctx.guild.id)
            await settings.update_or_add()

        # None-safe - nonexistent or non-configured role return None
        member_role = ctx.guild.get_role(settings.member_role)
        if member_role is not None:
            targets = {member_role}
        else:
            await ctx.send(
                '{0.author.mention}, the members role has not been configured. This may not work as expected. Use '
                '`{0.prefix}help memberconfig` to see how to set this up.'.format(
                    ctx))
            targets = set(sorted(ctx.guild.roles)[:ctx.author.top_role.position])

        to_restore = [(target, ctx.channel.overwrites_for(target)) for target in targets]
        for target, overwrite in to_restore:
            new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages=False, add_reactions=False)
            await ctx.channel.set_permissions(target, overwrite=new_overwrite)

        for allow_target in (ctx.me, ctx.author):
            overwrite = ctx.channel.overwrites_for(allow_target)
            new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages=True)
            await ctx.channel.set_permissions(allow_target, overwrite=new_overwrite)
            to_restore.append((allow_target, overwrite))

        e = discord.Embed(title='Timeout - {}s'.format(duration), description='This channel has been timed out.',
                          color=discord.Color.blue())
        e.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url_as(format='png', size=32))
        msg = await ctx.send(embed=e)

        await asyncio.sleep(duration)

        for target, overwrite in to_restore:
            if all(permission is None for _, permission in overwrite):
                await ctx.channel.set_permissions(target, overwrite=None)
            else:
                await ctx.channel.set_permissions(target, overwrite=overwrite)

        e.description = 'The timeout has ended.'
        await msg.edit(embed=e)
    timeout.example_usage = """
    `{prefix}timeout 60` - prevents sending messages in this channel for 1 minute (60s)
    """

    @command(aliases=["purge"])
    @has_permissions(manage_messages=True)
    @bot_has_permissions(manage_messages=True, read_message_history=True)
    async def prune(self, ctx, num_to_delete: int):
        """Bulk delete a set number of messages from the current channel."""
        await ctx.message.channel.purge(limit=num_to_delete + 1)
        await ctx.send(
            "Deleted {n} messages under request of {user}".format(n=num_to_delete, user=ctx.message.author.mention),
            delete_after=5)
    prune.example_usage = """
    `{prefix}prune 10` - Delete the last 10 messages in the current channel.
    """

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def ban(self, ctx, user_mention: discord.User, *, reason="No reason provided"):
        """Bans the user mentioned."""
        await self.mod_log(actor=ctx.author, action="banned", target=user_mention, reason=reason, orig_channel=ctx.channel)
        await ctx.guild.ban(user_mention, reason=reason)
    ban.example_usage = """
    `{prefix}ban @user reason - ban @user for a given (optional) reason
    """

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_mention: discord.User, *, reason="No reason provided"):
        """Unbans the user mentioned."""
        await ctx.guild.unban(user_mention, reason=reason)
        await self.mod_log(actor=ctx.author, action="banned", target=user_mention, reason=reason, orig_channel=ctx.channel)
    unban.example_usage = """
    `{prefix}unban user_id reason - unban the user corresponding to the ID for a given (optional) reason
    """

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(kick_members=True)
    async def kick(self, ctx, user_mention: discord.User, *, reason="No reason provided"):
        """Kicks the user mentioned."""
        await self.mod_log(actor=ctx.author, action="kicked", target=user_mention, reason=reason, orig_channel=ctx.channel)
        await ctx.guild.kick(user_mention, reason=reason)
    kick.example_usage = """
    `{prefix}kick @user reason - kick @user for a given (optional) reason
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_roles=True)
    async def mute(self, ctx, member_mentions: discord.Member, *, reason="No reason provided"):
        """Mute a user to prevent them from sending messages"""
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub(reason, "") or "No reason provided"
            if await self._mute(member_mentions, reason=reason, seconds=seconds, actor=ctx.author, orig_channel=ctx.channel):
                await self.mod_log(ctx.author, "muted", member_mentions, reason, ctx.channel, discord.Color.red())
            else:
                await ctx.send("Member is already muted!")
    mute.example_usage = """
    `{prefix}mute @user 1h reason` - mute @user for 1 hour for a given reason, the timing component (1h) and reason is optional.
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx, member_mentions: discord.Member, reason="No reason provided"):
        """Unmute a user to allow them to send messages again."""
        async with ctx.typing():
            if await self._unmute(member_mentions):
                await self.mod_log(actor=ctx.author, action="unmuted", target=member_mentions, reason=reason,
                                   orig_channel=ctx.channel, embed_color=discord.Color.green())
            else:
                await ctx.send("Member is not muted!")
    unmute.example_usage = """
    `{prefix}unmute @user reason - unmute @user for a given (optional) reason
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_roles=True)
    async def deafen(self, ctx, member_mentions: discord.Member, *, reason="No reason provided"):
        """Deafen a user to prevent them from both sending messages but also reading messages."""
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub(reason, "") or "No reason provided"
            if await self._deafen(member_mentions, reason, seconds=seconds, self_inflicted=False, actor=ctx.author, orig_channel=ctx.channel):
                await self.mod_log(ctx.author, "deafened", member_mentions, reason, ctx.channel, discord.Color.red())
            else:
                await ctx.send("Member is already deafened!")

    deafen.example_usage = """
    `{prefix}deafen @user 1h reason` - deafen @user for 1 hour for a given reason, the timing component (1h) is optional.
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    async def selfdeafen(self, ctx, *, reason="No reason provided"):
        """Deafen yourself for a given time period to prevent you from reading or sending messages; useful as a study tool."""
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub(reason, "") or "No reason provided"
            if await self._deafen(ctx.author, reason, seconds=seconds, self_inflicted=True, actor=ctx.author, orig_channel=ctx.channel):
                await self.mod_log(ctx.author, "deafened", ctx.author, reason, ctx.channel, discord.Color.red(), global_modlog=False)
            else:
                await ctx.send("You are already deafened!")

    selfdeafen.example_usage = """
    `{prefix}selfdeafen time (1h5m, both optional) reason`: deafens you if you need to get work done
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_roles=True)
    async def undeafen(self, ctx, member_mentions: discord.Member, reason="No reason provided"):
        """Undeafen a user to allow them to see message and send message again."""
        async with ctx.typing():
            await self._undeafen(member_mentions, reason, ctx)
    undeafen.example_usage = """
    `{prefix}undeafen @user reason - undeafen @user for a given (optional) reason
    """

    @command()
    async def voicekick(self, ctx, member: discord.Member, reason="No reason provided"):
        """Kick a user from voice chat. This is most useful if their perms to rejoin have already been removed."""
        async with ctx.typing():
            if member.voice is None:
                await ctx.send("User is not in a voice channel!")
                return
            if not member.voice.channel.permissions_for(ctx.author).move_members:
                await ctx.send("You do not have permission to do this!")
                return
            if not member.voice.channel.permissions_for(ctx.me).move_members:
                await ctx.send("I do not have permission to do this!")
                return
            await member.edit(voice_channel=None, reason=reason)
            await ctx.send(f"{member} has been kicked from voice chat.")
    voicekick.example_usage = """
    `{prefix}voicekick @user reason` - kick @user out of voice
    """

    """=== Configuration commands ==="""

    @command()
    @has_permissions(administrator=True)
    async def modlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        config = await GuildModLog.get_by_guild(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.name = ctx.guild.name
            config.modlog_channel = channel_mentions.id
        else:
            config = GuildModLog(guild_id=ctx.guild.id, modlog_channel=channel_mentions.id, name=ctx.guild.name)
        await config.update_or_add()
        await ctx.send(ctx.message.author.mention + ', modlog settings configured!')
    modlogconfig.example_usage = """
    `{prefix}modlogconfig #join-leave-logs` - set a channel named #join-leave-logs to log joins/leaves 
    """

    @command()
    @has_permissions(administrator=True)
    async def nmconfig(self, ctx, channel_mention: discord.TextChannel, role: discord.Role, *, message):
        """Sets the config for the new members channel"""
        config = await GuildNewMember.get_by_guild(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.channel_id = channel_mention.id
            config.role_id = role.id
            config.message = message.casefold()
        else:
            config = GuildNewMember(guild_id=ctx.guild.id, channel_id=channel_mention.id, role_id=role.id,
                                    message=message.casefold())
        await config.update_or_add()

        role_name = role.name
        await ctx.send(
            "New Member Channel configured as: {channel}. Role configured as: {role}. Message: {message}".format(
                channel=channel_mention.name, role=role_name, message=message))
    nmconfig.example_usage = """
    `{prefix}nmconfig #new_members Member I have read the rules and regulations` - Configures the #new_members channel 
    so if someone types "I have read the rules and regulations" it assigns them the Member role. 
    """

    @command()
    @has_permissions(administrator=True)
    async def memberconfig(self, ctx, *, member_role: SafeRoleConverter):
        """
        Set the member role for the guild.
        The member role is the role used for the timeout command. It should be a role that all members of the server have.
        """
        if member_role >= ctx.author.top_role:
            raise BadArgument('member role cannot be higher than your top role!')

        settings = await MemberRole.get_by_guild(guild_id=ctx.guild.id)
        if settings is None:
            settings = MemberRole(guild_id=ctx.guild.id, member_role=member_role.id)
        else:
            settings = settings[0]
            settings.member_role = member_role.id
        await settings.update_or_add()
        await ctx.send('Member role set as `{}`.'.format(member_role.name))
    memberconfig.example_usage = """
    `{prefix}memberconfig Members` - set a role called "Members" as the member role
    `{prefix}memberconfig @everyone` - set the default role as the member role
    `{prefix}memberconfig everyone` - set the default role as the member role (ping-safe)
    `{prefix}memberconfig @ everyone` - set the default role as the member role (ping-safe)
    `{prefix}memberconfig @.everyone` - set the default role as the member role (ping-safe)
    `{prefix}memberconfig @/everyone` - set the default role as the member role (ping-safe)
    """

    @command()
    @has_permissions(administrator=True)
    @bot_has_permissions(manage_messages=True)
    async def linkscrubconfig(self, ctx, *, link_role: SafeRoleConverter):
        """
        Set a role that users must have in order to post links.
        This accepts the safe default role conventions that the memberconfig command does.
        """
        if link_role >= ctx.author.top_role:
            raise BadArgument('Link role cannot be higher than your top role!')

        settings = await GuildMessageLinks.get_by_guild(guild_id=ctx.guild.id)
        if len(settings) == 0:
            settings = GuildMessageLinks(guild_id=ctx.guild.id, role_id=link_role.id)
        else:
            settings = settings[0]
            settings.role_id = link_role.id
        await settings.update_or_add()
        self.links_config.invalidate_entry(guild_id=ctx.guild.id)
        await ctx.send(f'Link role set as `{link_role.name}`.')
    linkscrubconfig.example_usage = """
    `{prefix}linkscrubconfig Links` - set a role called "Links" as the link role
    `{prefix}linkscrubconfig @everyone` - set the default role as the link role
    `{prefix}linkscrubconfig everyone` - set the default role as the link role (ping-safe)
    `{prefix}linkscrubconfig @ everyone` - set the default role as the link role (ping-safe)
    `{prefix}linkscrubconfig @.everyone` - set the default role as the link role (ping-safe)
    `{prefix}linkscrubconfig @/everyone` - set the default role as the link role (ping-safe)
    """

    @command()
    @has_permissions(administrator=True)
    async def memberlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the join/leave channel for a server by passing a channel mention"""
        config = await GuildMemberLog.get_by_guild(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.name = ctx.guild.name
            config.memberlog_channel = channel_mentions.id
        else:
            config = GuildMemberLog(guild_id=ctx.guild.id, memberlog_channel=channel_mentions.id, name=ctx.guild.name)
        await config.update_or_add()
        await ctx.send(ctx.message.author.mention + ', memberlog settings configured!')
    memberlogconfig.example_usage = """
    `{prefix}memberlogconfig #join-leave-logs` - set a channel named #join-leave-logs to log joins/leaves 
    """

    @command()
    @has_permissions(administrator=True)
    async def messagelogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        config = await GuildMessageLog.get_by_guild(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.name = ctx.guild.name
            config.messagelog_channel = channel_mentions.id
        else:
            config = GuildMessageLog(guild_id=ctx.guild.id, messagelog_channel=channel_mentions.id, name=ctx.guild.name)
        await config.update_or_add()
        # self.edit_delete_config.invalidate_entry(id=ctx.guild.id)
        await ctx.send(ctx.message.author.mention + ', messagelog settings configured!')
    messagelogconfig.example_usage = """
    `{prefix}messagelogconfig #orwellian-dystopia` - set a channel named #orwellian-dystopia to log message edits/deletions
    """


# class Mute(db.DatabaseObject):
#     """Provides a DB config to track mutes."""
#     __tablename__ = 'mutes'
#     id = db.Column(db.BigInteger, primary_key=True)
#     guild = db.Column(db.BigInteger, primary_key=True)
#     past_participle = "muted"
#     finished_callback = Moderation._unmute
#     type = 1

class Mute(db.DatabaseTable):
    type = 1
    past_participle = "muted"
    finished_callback = Moderation._unmute
    __tablename__ = 'mutes'
    __uniques__ = 'guild_id, member_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            member_id bigint,
            guild_id bigint,
            PRIMARY KEY (member_id, guild_id)
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, member_id, guild_id):
        super().__init__()
        self.member_id = member_id
        self.guild_id = guild_id

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = Mute(member_id=result.get("member_id"), guild_id=result.get("guild_id"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list

    async def update_or_add(cls):
        values = [cls.member_id, cls.guild_id]
        keys = ["member_id", "guild_id"]
        async with db.Pool.acquire() as conn:
            statement = f"""
            INSERT INTO {cls.__tablename__} ({", ".join(keys)})
            VALUES({','.join(f'${i+1}' for i in range(len(values)))}) 
            """
            print(statement)
            for value in values:
                print(value, type(value))
            await conn.execute(statement, *values)


# class Deafen(db.DatabaseObject):
#     """Provides a DB config to track deafens."""
#     __tablename__ = 'deafens'
#     id = db.Column(db.BigInteger, primary_key=True)
#     guild = db.Column(db.BigInteger, primary_key=True)
#     self_inflicted = db.Column(db.Boolean)
#     past_participle = "deafened"
#     finished_callback = Moderation._undeafen
#     type = 2

class Deafen(db.DatabaseTable):
    type = 2
    __tablename__ = 'deafens'
    __uniques__ = 'member_id, guild_id'
    past_participle = "deafened"
    finished_callback = Moderation._undeafen
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            member_id bigint,
            guild_id bigint,
            self_inflicted boolean,
            PRIMARY KEY (member_id, guild_id)
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, member_id, guild_id, self_inflicted):
        super().__init__()
        self.member_id = member_id
        self.guild_id = guild_id
        self.self_inflicted = self_inflicted

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = Deafen(member_id=result.get("member_id"), guild_id=result.get("guild_id"),
                             self_inflicted=result.get("self_inflicted"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list


# class GuildModLog(db.DatabaseObject):
#     """Provides a DB config to track which channel a guild uses for modlogs."""
#     __tablename__ = 'modlogconfig'
#     id = db.Column(db.BigInteger, primary_key=True)
#     name = db.Column(db.String)
#     modlog_channel = db.Column(db.BigInteger, nullable=True)

class GuildModLog(db.DatabaseTable):
    __tablename__ = 'modlogconfig'
    __uniques__ = 'guild_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            modlog_channel bigint null,
            name varchar
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, modlog_channel, name):
        super().__init__()
        self.guild_id = guild_id
        self.modlog_channel = modlog_channel
        self.name = name

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = GuildModLog(guild_id=result.get("guild_id"), modlog_channel=result.get("modlog_channel"),
                                  name=result.get("name"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list


# class MemberRole(db.DatabaseObject):
#     """Keeps track of member roles."""
#     __tablename__ = 'member_roles'
#     id = db.Column(db.BigInteger, primary_key=True)
#     member_role = db.Column(db.BigInteger, nullable=True)

class MemberRole(db.DatabaseTable):
    __tablename__ = 'member_roles'
    __uniques__ = 'guild_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            member_role bigint null
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, member_role=None):
        super().__init__()
        self.guild_id = guild_id
        self.member_role = member_role

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = MemberRole(member_role=result.get("member_role"), guild_id=result.get("guild_id"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list

    async def update_or_add(cls):
        values = [cls.member_role, cls.guild_id]
        keys = ["member_role", "guild_id"]
        async with db.Pool.acquire() as conn:
            statement = f"""
            INSERT INTO {cls.__tablename__} ({", ".join(keys)})
            VALUES({','.join(f'${i+1}' for i in range(len(values)))}) 
            ON CONFLICT (guild_id) DO UPDATE
            SET member_role = excluded.member_role;
            """
            print(statement)
            for value in values:
                print(value, type(value))
            await conn.execute(statement, *values)


# class GuildNewMember(db.DatabaseObject):
#     """Keeps track of things for onboarding new server members."""
#     __tablename__ = 'new_members'
#     guild_id = db.Column(db.BigInteger, primary_key=True)
#     channel_id = db.Column(db.BigInteger)
#     role_id = db.Column(db.BigInteger)
#     message = db.Column(db.String)

class GuildNewMember(db.DatabaseTable):
    __tablename__ = 'new_members'
    __uniques__ = 'guild_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            channel_id bigint,
            role_id bigint,
            message varchar
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, channel_id, role_id, message):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.role_id = role_id
        self.message = message

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = GuildNewMember(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                     role_id=result.get("role_id"), message=result.get("message"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list


# class GuildMemberLog(db.DatabaseObject):
#     """Keeps track of which channels guilds use for member logs."""
#     __tablename__ = 'memberlogconfig'
#     id = db.Column(db.BigInteger, primary_key=True)
#     name = db.Column(db.String)
#     memberlog_channel = db.Column(db.BigInteger)

class GuildMemberLog(db.DatabaseTable):
    __tablename__ = 'memberlogconfig'
    __uniques__ = 'guild_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            memberlog_channel bigint,
            name varchar
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, memberlog_channel, name):
        super().__init__()
        self.guild_id = guild_id
        self.memberlog_channel = memberlog_channel
        self.name = name

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = GuildMemberLog(guild_id=result.get("guild_id"), memberlog_channel=result.get("memberlog_channel"),
                                     name=result.get("name"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list


# class GuildMessageLog(db.DatabaseObject):
#     """Keeps track of which channels use for message edit/deletion logs."""
#     __tablename__ = 'messagelogconfig'
#     id = db.Column(db.BigInteger, primary_key=True)
#     name = db.Column(db.String)
#     messagelog_channel = db.Column(db.BigInteger)

class GuildMessageLog(db.DatabaseTable):
    __tablename__ = 'messagelogconfig'
    __uniques__ = 'guild_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            name varchar,
            messagelog_channel bigint
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, name, messagelog_channel):
        super().__init__()
        self.guild_id = guild_id
        self.name = name
        self.messagelog_channel = messagelog_channel

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = GuildMessageLog(guild_id=result.get("guild_id"), name=result.get("name"),
                                      messagelog_channel=result.get("messagelog_channel"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list


# class GuildMessageLinks(db.DatabaseObject):
#     """Keeps track of message links settings in guilds."""
#     __tablename__ = 'guild_msg_links'
#     guild_id = db.Column(db.BigInteger, primary_key=True)
#     role_id = db.Column(db.BigInteger, nullable=True)

class GuildMessageLinks(db.DatabaseTable):
    __tablename__ = 'guild_msg_links'
    __uniques__ = 'guild_id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            role_id bigint null
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, role_id=None):
        super().__init__()
        self.guild_id = guild_id
        self.role_id = role_id

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = GuildMessageLinks(guild_id=result.get("guild_id"), role_id=result.get("role_id"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list


# class PunishmentTimerRecord(db.DatabaseObject):
#     """Keeps track of current punishment timers in case the bot is restarted."""
#     __tablename__ = "punishment_timers"
#     id = db.Column(db.BigInteger, primary_key=True)
#     guild_id = db.Column(db.BigInteger)
#     actor_id = db.Column(db.BigInteger)
#     target_id = db.Column(db.BigInteger)
#     orig_channel_id = db.Column(db.BigInteger, nullable=True)
#     type = db.Column(db.BigInteger)
#     reason = db.Column(db.String, nullable=True)
#     target_ts = db.Column(db.BigInteger)
#
#     type_map = {p.type: p for p in (Mute, Deafen)}

class PunishmentTimerRecord(db.DatabaseTable):
    type_map = {p.type: p for p in (Mute, Deafen)}
    __tablename__ = 'punishment_timers'
    __uniques__ = 'id'
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY,
            guild_id bigint,
            actor_id bigint,
            target_id bigint,
            orig_channel_id bigint null,
            type_of_punishment bigint,
            reason varchar null,
            target_ts bigint
            )""")

    # @classmethod
    # async def initial_migrate(cls):
    #     async with db.Pool.acquire() as conn:
    #         await conn.execute("""ALTER TABLE welcome_channel RENAME id TO guild_id""")

    def __init__(self, guild_id, actor_id, target_id, type_of_punishment, target_ts, orig_channel_id=None, reason=None):
        super().__init__()
        self.guild_id = guild_id
        self.actor_id = actor_id
        self.target_id = target_id
        self.type_of_punishment = type_of_punishment
        self.target_ts = target_ts
        self.orig_channel_id = orig_channel_id
        self.reason = reason

    async def get_by_attribute(self, obj_id, column_name):
        """Gets a list of all objects with a given attribute"""
        async with db.Pool.acquire() as conn:  # Use transaction here?
            results = await conn.fetch(f"""SELECT * FROM {self.__tablename__} WHERE {column_name} = {obj_id}""")
            list = []
            for result in results:
                obj = PunishmentTimerRecord(guild_id=result.get("guild_id"), actor_id=result.get("actor_id"),
                                            target_id=result.get("target_id"),
                                            type_of_punishment=result.get("type_of_punishment"),
                                            target_ts=result.get("target_ts"),
                                            orig_channel_id=result.get("orig_channel_id"), reason=result.get("reason"))
                # for var in obj.__dict__:
                #     setattr(obj, var, result.get(var))
                list.append(obj)
            return list


def setup(bot):
    """Adds the moderation cog to the bot."""
    bot.add_cog(Moderation(bot))
