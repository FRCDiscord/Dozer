"""Provides moderation commands for Dozer."""
import asyncio
import re
import datetime
import time
from typing import Union
from logging import getLogger

import discord
from discord import Forbidden
from discord.ext.commands import BadArgument, has_permissions, RoleConverter

from ._utils import *
from .. import db

MAX_PURGE = 1000

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

    @staticmethod
    async def check_audit(guild, event_time=None):
        """Method for checking the audit log for events"""
        try:
            async for entry in guild.audit_logs(limit=1, before=event_time, action=discord.AuditLogAction.message_delete):
                return entry
        except Forbidden:
            return None

    async def nm_kick_internal(self, guild=None):
        """Kicks people who have not done the new member process within a set amount of time."""
        getLogger("dozer").debug("Starting nm_kick cycle...")
        if not guild:
            entries = await NewMemPurgeConfig.get_by()
        else:
            entries = await NewMemPurgeConfig.get_by(guild_id=guild.id)
        count = 0
        for entry in entries:
            guild = self.bot.get_guild(entry.guild_id)
            if guild is None:
                continue
            for mem in guild.members:
                if guild.get_role(entry.member_role) not in mem.roles:
                    delta = datetime.datetime.now() - mem.joined_at
                    if delta.days >= entry.days:
                        await mem.kick(reason="New member purge cycle")
                        count += 1
        return count

    @discord.ext.tasks.loop(hours=168)
    async def nm_kick(self):
        await self.nm_kick_internal()

    async def mod_log(self, actor: discord.Member, action: str, target: Union[discord.User, discord.Member, None], reason, orig_channel=None,
                      embed_color=discord.Color.red(), global_modlog=True, duration=None):
        """Generates a modlog embed"""

        if target is None:
            title = "Custom Modlog"
        else:
            title = f"User {action}!"

        modlog_embed = discord.Embed(
            color=embed_color,
            title=title

        )
        if target is not None:
            modlog_embed.add_field(name=f"{action.capitalize()} user", value=f"{target.mention} ({target} | {target.id})", inline=False)
        modlog_embed.add_field(name="Requested by", value=f"{actor.mention} ({actor} | {actor.id})", inline=False)
        modlog_embed.add_field(name="Reason", value=reason or "No reason specified", inline=False)
        modlog_embed.timestamp = datetime.datetime.utcnow()
        if duration:
            modlog_embed.add_field(name="Duration", value=duration)
        if target is not None:
            try:
                await target.send(embed=modlog_embed)
            except discord.Forbidden:
                await orig_channel.send("Failed to DM modlog to user")
        modlog_channel = await GuildModLog.get_by(guild_id=actor.guild.id)
        if orig_channel is not None:
            await orig_channel.send(embed=modlog_embed)
        if len(modlog_channel) != 0:
            if global_modlog:
                channel = actor.guild.get_channel(modlog_channel[0].modlog_channel)
                if channel is not None and channel != orig_channel:  # prevent duplicate embeds
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
        ent = PunishmentTimerRecords(
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

        user = await punishment.get_by(member_id=target.id)
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
            await PunishmentTimerRecords.delete(guild_id=target.guild.id, target_id=target.id, type_of_punishment=punishment.type)

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
        results = await Mute.get_by(guild_id=member.guild.id, member_id=member.id)
        if results:
            return False  # member already muted
        else:
            user = Mute(member_id=member.id, guild_id=member.guild.id)
            await user.update_or_add()
            await self.perm_override(member, send_messages=False, add_reactions=False, speak=False)

            self.bot.loop.create_task(
                self.punishment_timer(seconds, member, Mute, reason, actor or member.guild.me, orig_channel=orig_channel))
            return True

    async def _unmute(self, member: discord.Member):
        """Unmutes a user."""
        results = await Mute.get_by(guild_id=member.guild.id, member_id=member.id)
        if results:
            await Mute.delete(member_id=member.id, guild_id=member.guild.id)
            await PunishmentTimerRecords.delete(target_id=member.id, guild_id=member.guild.id, type_of_punishment=Mute.type)
            await self.perm_override(member, send_messages=None, add_reactions=None, speak=None)
            return True
        else:
            return False  # member not muted

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
        results = await Deafen.get_by(guild_id=member.guild.id, member_id=member.id)
        if results:
            return False
        else:
            user = Deafen(member_id=member.id, guild_id=member.guild.id, self_inflicted=self_inflicted)
            await user.update_or_add()
            await self.perm_override(member, read_messages=False)

            if self_inflicted and seconds == 0:
                seconds = 30  # prevent lockout in case of bad argument
            self.bot.loop.create_task(
                self.punishment_timer(seconds, member,
                                      punishment=Deafen,
                                      reason=reason,
                                      actor=actor or member.guild.me,
                                      orig_channel=orig_channel,
                                      global_modlog=not self_inflicted))
            return True

    async def _undeafen(self, member: discord.Member):
        """Undeafens a user."""
        results = await Deafen.get_by(guild_id=member.guild.id, member_id=member.id)
        if results:
            await self.perm_override(member=member, read_messages=None)
            await PunishmentTimerRecords.delete(target_id=member.id, guild_id=member.guild.id, type_of_punishment=Deafen.type)
            await Deafen.delete(member_id=member.id, guild_id=member.guild.id)
            truths = [True, results[0].self_inflicted]
            return truths
        else:
            return [False]

    """=== Event handlers ==="""

    @Cog.listener('on_ready')
    async def on_ready(self):
        """Restore punishment timers on bot startup and trigger the nm purge cycle"""
        await self.nm_kick.start()
        q = await PunishmentTimerRecords.get_by()  # no filters: all
        for r in q:
            guild = self.bot.get_guild(r.guild_id)
            actor = guild.get_member(r.actor_id)
            target = guild.get_member(r.target_id)
            orig_channel = self.bot.get_channel(r.orig_channel_id)
            punishment_type = r.type_of_punishment
            reason = r.reason or ""
            seconds = max(int(r.target_ts - time.time()), 0.01)
            await PunishmentTimerRecords.delete(id=r.id)
            self.bot.loop.create_task(self.punishment_timer(seconds, target, PunishmentTimerRecords.type_map[punishment_type], reason, actor,
                                                            orig_channel))
            getLogger('dozer').info(f"Restarted {PunishmentTimerRecords.type_map[punishment_type].__name__} of {target} in {guild}")

    @Cog.listener('on_member_join')
    async def on_member_join(self, member):
        """Logs that a member joined."""
        join = discord.Embed(type='rich', color=0x00FF00)
        join.set_author(name='Member Joined', icon_url=member.avatar_url_as(format='png', size=32))
        join.description = "{0.mention}\n{0} ({0.id})".format(member)
        join.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
        member_log_channel = await GuildMemberLog.get_by(guild_id=member.guild.id)
        if len(member_log_channel) != 0:
            channel = member.guild.get_channel(member_log_channel[0].memberlog_channel)
            await channel.send(embed=join)
        users = await Mute.get_by(guild_id=member.guild.id, member_id=member.id)
        if users:
            await self.perm_override(member, add_reactions=False, send_messages=False)
        users = await Deafen.get_by(guild_id=member.guild.id, member_id=member.id)
        if users:
            await self.perm_override(member, read_messages=False)

    @Cog.listener('on_member_remove')
    async def on_member_remove(self, member):
        """Logs that a member left."""
        leave = discord.Embed(type='rich', color=0xFF0000)
        leave.set_author(name='Member Left', icon_url=member.avatar_url_as(format='png', size=32))
        leave.description = "{0.mention}\n{0} ({0.id})".format(member)
        leave.set_footer(text="{} | {} members".format(member.guild.name, member.guild.member_count))
        member_log_channel = await GuildMemberLog.get_by(guild_id=member.guild.id)
        if len(member_log_channel) != 0:
            channel = member.guild.get_channel(member_log_channel[0].memberlog_channel)
            await channel.send(embed=leave)

    @Cog.listener('on_message')
    async def on_message(self, message):
        """Check things when messages come in."""
        if message.author.bot or message.guild is None or not message.guild.me.guild_permissions.manage_roles:
            return
        if await self.check_links(message):
            return
        config = await GuildNewMember.get_by(guild_id=message.guild.id)
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

    @Cog.listener()
    async def on_raw_message_delete(self, payload):
        """When a message is deleted and its not in the bot cache, log it anyway."""
        if payload.cached_message:
            return
        guild = self.bot.get_guild(int(payload.guild_id))
        message_channel = self.bot.get_channel(int(payload.channel_id))
        message_id = int(payload.message_id)
        message_created = discord.Object(message_id).created_at
        embed = discord.Embed(title="Message Deleted",
                              description=f"Message Deleted In: {message_channel.mention}",
                              color=0xFF00F0, timestamp=message_created)
        embed.add_field(name="Message", value="N/A", inline=False)
        embed.set_footer(text=f"MessageID: {message_id}; Sent at")
        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener('on_message_delete')
    async def on_message_delete(self, message):
        """When a message is deleted, log it."""
        if message.author == self.bot.user:
            return
        audit = await self.check_audit(message.guild)
        embed = discord.Embed(title="Message Deleted",
                              description=f"Message Deleted In: {message.channel.mention}\nSent by: {message.author.mention}",
                              color=0xFF0000, timestamp=message.created_at)
        embed.set_author(name=message.author, icon_url=message.author.avatar_url)
        if audit:
            if audit.target == message.author:
                audit_member = await message.guild.fetch_member(audit.user.id)
                embed.add_field(name="Message Deleted By: ", value=str(audit_member.mention), inline=False)
        if message.content:
            embed.add_field(name="Message Content:", value=message.content[0:1023], inline=False)
            if len(message.content) > 1024:
                embed.add_field(name="Message Content Continued:", value=message.content[1024:2000], inline=False)
        else:
            embed.add_field(name="Message Content:", value="N/A", inline=False)
        embed.set_footer(text=f"UserID: {message.author.id}")
        if message.attachments:
            embed.add_field(name="Attachments", value=", ".join([i.url for i in message.attachments]))
        message_log_channel = await self.edit_delete_config.query_one(guild_id=message.guild.id)
        if message_log_channel is not None:
            channel = message.guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener()
    async def on_raw_message_edit(self, payload):
        """Logs message edits that are not currently in the bots message cache"""
        if payload.cached_message:
            return
        mchannel = self.bot.get_channel(int(payload.channel_id))
        guild = mchannel.guild
        try:
            content = payload.data['content']
        except KeyError:
            content = None
        author = payload.data.get("author")
        if not author:
            return
        guild_id = guild.id
        channel_id = payload.channel_id
        user_id = author['id']
        if (self.bot.get_user(int(user_id))).bot:
            return  # Breakout if the user is a bot
        message_id = payload.message_id
        link = f"https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}"
        mention = f"<@!{user_id}>"
        avatar_link = f"http://cdn.discordapp.com/avatars/{user_id}/{author['avatar']}.webp?size=1024"
        embed = discord.Embed(title="Message Edited",
                              description=f"[MESSAGE]({link}) From {mention}\nEdited In: {mchannel.mention}", color=0xFFC400)
        embed.set_author(name=f"{author['username']}#{author['discriminator']}",icon_url=avatar_link)
        embed.add_field(name="Original", value="N/A", inline=False)
        if content:
            embed.add_field(name="Edited", value=content[0:1023], inline=False)
            if len(content) > 1024:
                embed.add_field(name="Edited Continued", value=content[1024:2000], inline=False)
        else:
            embed.add_field(name="Edited", value="N/A", inline=False)
        embed.set_footer(text=f"UserID: {user_id}")
        message_log_channel = await self.edit_delete_config.query_one(guild_id=guild.id)
        if message_log_channel is not None:
            channel = guild.get_channel(message_log_channel.messagelog_channel)
            if channel is not None:
                await channel.send(embed=embed)

    @Cog.listener('on_message_edit')
    async def on_message_edit(self, before, after):
        """Logs message edits."""
        await self.check_links(after)
        if before.author.bot:
            return
        if after.edited_at is not None or before.edited_at is not None:
            # There is a reason for this. That reason is that otherwise, an infinite spam loop occurs
            guild_id = before.guild.id
            channel_id = before.channel.id
            user_id = before.author.id
            message_id = before.id
            link = f"https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}"
            embed = discord.Embed(title="Message Edited",
                                  description=f"[MESSAGE]({link}) From {before.author.mention}"
                                              f"\nEdited In: {before.channel.mention}", color=0xFFC400,
                                  timestamp=after.edited_at)
            embed.set_author(name=before.author, icon_url=before.author.avatar_url)
            if before.content:
                embed.add_field(name="Original", value=before.content[0:1023], inline=False)
                if len(before.content) > 1024:
                    embed.add_field(name="Original Continued", value=before.content[1024:2000], inline=False)
                embed.add_field(name="Edited", value=after.content[0:1023], inline=False)
                if len(after.content) > 1024:
                    embed.add_field(name="Edited Continued", value=after.content[1024:2000], inline=False)
            else:
                embed.add_field(name="Original", value="N/A", inline=False)
                embed.add_field(name="Edited", value="N/A", inline=False)
            embed.set_footer(text=f"UserID: {user_id}")
            if after.attachments:
                embed.add_field(name="Attachments", value=", ".join([i.url for i in before.attachments]))
            message_log_channel = await self.edit_delete_config.query_one(guild_id=before.guild.id)
            if message_log_channel is not None:
                channel = before.guild.get_channel(message_log_channel.messagelog_channel)
                if channel is not None:
                    await channel.send(embed=embed)

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
    @has_permissions(kick_members=True)
    async def customlog(self, ctx, *, reason):
        """Sends a message to the mod log with custom text."""
        await self.mod_log(actor=ctx.author, action="", target=None, orig_channel=ctx.channel, reason=reason, embed_color=0xFFC400)

    customlog.example_usage = """
    `{prefix}`customlog reason - warns a user for "reason"
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_roles=True)
    async def timeout(self, ctx, duration: float):
        """Set a timeout (no sending messages or adding reactions) on the current channel."""
        settings = await MemberRole.get_by(guild_id=ctx.guild.id)
        if len(settings) == 0:
            settings = MemberRole(guild_id=ctx.guild.id, member_role=MemberRole.nullify)
            await settings.update_or_add()
        else:
            settings = settings[0]
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
    async def prune(self, ctx, num: int):
        """Bulk delete a set number of messages from the current channel."""
        try:
            msg = await ctx.message.channel.fetch_message(num)
            deleted = await ctx.message.channel.purge(after=msg, limit=MAX_PURGE)
            await ctx.send(
                f"Deleted {len(deleted)} messages under request of {ctx.message.author.mention}",
                delete_after=5)
        except discord.NotFound:
            if num > MAX_PURGE:
                await ctx.send("Message cannot be found or you're trying to purge too many messages.")
                return
            deleted = await ctx.message.channel.purge(limit=num + 1)
            await ctx.send(
                f"Deleted {len(deleted) - 1} messages under request of {ctx.message.author.mention}",
                delete_after=5)

    prune.example_usage = """
    `{prefix}prune 10` - Delete the last 10 messages in the current channel.
    `{prefix}prune 786324930378727484` - Deletes all messages up to that message ID
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
            reason = self.hm_regex.sub("", reason) or "No reason provided"
            if await self._mute(member_mentions, reason=reason, seconds=seconds, actor=ctx.author, orig_channel=ctx.channel):
                await self.mod_log(ctx.author, "muted", member_mentions, reason, ctx.channel, discord.Color.red(),
                                   duration=datetime.timedelta(seconds=seconds))
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
            reason = self.hm_regex.sub("", reason) or "No reason provided"
            if await self._deafen(member_mentions, reason, seconds=seconds, self_inflicted=False, actor=ctx.author, orig_channel=ctx.channel):
                await self.mod_log(ctx.author, "deafened", member_mentions, reason, ctx.channel, discord.Color.red(),
                                   duration=datetime.timedelta(seconds=seconds))
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
            reason = self.hm_regex.sub("", reason) or "No reason provided"
            if await self._deafen(ctx.author, reason, seconds=seconds, self_inflicted=True, actor=ctx.author, orig_channel=ctx.channel):
                await self.mod_log(ctx.author, "deafened", ctx.author, reason, ctx.channel, discord.Color.red(), global_modlog=False,
                                   duration=datetime.timedelta(seconds=seconds))
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
            result = await self._undeafen(member_mentions)
            if result[0]:
                await self.mod_log(actor=ctx.author, action="undeafened", target=member_mentions, reason=reason,
                                   orig_channel=ctx.channel, embed_color=discord.Color.green(), global_modlog=not result[1])
            else:
                await ctx.send("Member is not deafened!")

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

    @has_permissions(kick_members=True)
    @bot_has_permissions(kick_members=True)
    @command()
    async def purgenm(self, ctx):
        """Manually run a new member purge"""
        memcount = await self.nm_kick_internal(guild=ctx.guild)
        await ctx.send(f"Kicked {memcount} members due to inactivity!")

    """=== Configuration commands ==="""

    @command()
    @has_permissions(administrator=True)
    async def modlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        config = await GuildModLog.get_by(guild_id=ctx.guild.id)
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
        config = await GuildNewMember.get_by(guild_id=ctx.guild.id)
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
    async def nmpurgeconfig(self, ctx, role: discord.Role, days: int):
        """Sets the config for the new members purge"""
        config = NewMemPurgeConfig(guild_id=ctx.guild.id, member_role=role.id, days=days)
        await config.update_or_add()

        await ctx.send("Settings saved!")

    nmpurgeconfig.example_usage = """
    `{prefix}nmpurgeconfig Members 90: Kicks everyone who doesn't have the members role 90 days after they join.
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

        settings = await MemberRole.get_by(guild_id=ctx.guild.id)
        if len(settings) == 0:
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

        settings = await GuildMessageLinks.get_by(guild_id=ctx.guild.id)
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
        config = await GuildMemberLog.get_by(guild_id=ctx.guild.id)
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
        config = await GuildMessageLog.get_by(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.name = ctx.guild.name
            config.messagelog_channel = channel_mentions.id
        else:
            config = GuildMessageLog(guild_id=ctx.guild.id, messagelog_channel=channel_mentions.id, name=ctx.guild.name)
        await config.update_or_add()
        self.edit_delete_config.invalidate_entry(id=ctx.guild.id)
        await ctx.send(ctx.message.author.mention + ', messagelog settings configured!')

    messagelogconfig.example_usage = """
    `{prefix}messagelogconfig #orwellian-dystopia` - set a channel named #orwellian-dystopia to log message edits/deletions
    """


class Mute(db.DatabaseTable):
    """Holds mute info"""
    type = 1
    past_participle = "muted"
    finished_callback = Moderation._unmute
    __tablename__ = 'mutes'
    __uniques__ = 'guild_id, member_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            member_id bigint NOT NULL,
            guild_id bigint NOT NULL,
            PRIMARY KEY (member_id, guild_id)
            )""")

    def __init__(self, member_id, guild_id):
        super().__init__()
        self.member_id = member_id
        self.guild_id = guild_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = Mute(member_id=result.get("member_id"), guild_id=result.get("guild_id"))
            result_list.append(obj)
        return result_list

    async def update_or_add(self):
        """Assign the attribute to this object, then call this method to either insert the object if it doesn't exist in
        the DB or update it if it does exist. It will update every column not specified in __uniques__."""
        # This is its own functions because all columns must be unique, which breaks the syntax of the other one
        keys = []
        values = []
        for var, value in self.__dict__.items():
            # Done so that the two are guaranteed to be in the same order, which isn't true of keys() and values()
            if value is not None:
                keys.append(var)
                values.append(value)
        async with db.Pool.acquire() as conn:
            statement = f"""
            INSERT INTO {self.__tablename__} ({", ".join(keys)})
            VALUES({','.join(f'${i + 1}' for i in range(len(values)))}) 
            """
            await conn.execute(statement, *values)


class Deafen(db.DatabaseTable):
    """Holds deafens"""
    type = 2
    __tablename__ = 'deafens'
    __uniques__ = 'member_id, guild_id'
    past_participle = "deafened"
    finished_callback = Moderation._undeafen

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            member_id bigint NOT NULL,
            guild_id bigint NOT NULL,
            self_inflicted boolean NOT NULL,
            PRIMARY KEY (member_id, guild_id)
            )""")

    def __init__(self, member_id, guild_id, self_inflicted):
        super().__init__()
        self.member_id = member_id
        self.guild_id = guild_id
        self.self_inflicted = self_inflicted

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = Deafen(member_id=result.get("member_id"), guild_id=result.get("guild_id"),
                         self_inflicted=result.get("self_inflicted"))
            result_list.append(obj)
        return result_list


class GuildModLog(db.DatabaseTable):
    """Holds modlog info"""
    __tablename__ = 'modlogconfig'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            modlog_channel bigint null,
            name varchar NOT NULL
            )""")

    def __init__(self, guild_id, modlog_channel, name):
        super().__init__()
        self.guild_id = guild_id
        self.modlog_channel = modlog_channel
        self.name = name

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildModLog(guild_id=result.get("guild_id"), modlog_channel=result.get("modlog_channel"),
                              name=result.get("name"))
            result_list.append(obj)
        return result_list


class MemberRole(db.DatabaseTable):
    """Holds info on member roles used for timeouts"""
    __tablename__ = 'member_roles'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            member_role bigint null
            )""")

    def __init__(self, guild_id, member_role=None):
        super().__init__()
        self.guild_id = guild_id
        self.member_role = member_role

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = MemberRole(member_role=result.get("member_role"), guild_id=result.get("guild_id"))
            result_list.append(obj)
        return result_list


class NewMemPurgeConfig(db.DatabaseTable):
    """Holds info on member purge routines"""
    __tablename__ = 'member_purge_configs'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            member_role bigint not null,
            days int not null
            )""")

    def __init__(self, guild_id, member_role, days):
        super().__init__()
        self.guild_id = guild_id
        self.member_role = member_role
        self.days = days

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = NewMemPurgeConfig(member_role=result.get("member_role"),
                                    guild_id=result.get("guild_id"),
                                    days=result.get("days"))
            result_list.append(obj)
        return result_list


class GuildNewMember(db.DatabaseTable):
    """Holds new member info"""
    __tablename__ = 'new_members'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            channel_id bigint NOT NULL,
            role_id bigint NOT NULL,
            message varchar NOT NULL
            )""")

    def __init__(self, guild_id, channel_id, role_id, message):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.role_id = role_id
        self.message = message

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildNewMember(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                 role_id=result.get("role_id"), message=result.get("message"))
            result_list.append(obj)
        return result_list


class GuildMemberLog(db.DatabaseTable):
    """Holds information for member logs"""
    __tablename__ = 'memberlogconfig'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            memberlog_channel bigint NOT NULL,
            name varchar NOT NULL
            )""")

    def __init__(self, guild_id, memberlog_channel, name):
        super().__init__()
        self.guild_id = guild_id
        self.memberlog_channel = memberlog_channel
        self.name = name

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildMemberLog(guild_id=result.get("guild_id"), memberlog_channel=result.get("memberlog_channel"),
                                 name=result.get("name"))
            result_list.append(obj)
        return result_list


class GuildMessageLog(db.DatabaseTable):
    """Holds config info for message logs"""
    __tablename__ = 'messagelogconfig'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            name varchar NOT NULL,
            messagelog_channel bigint NOT NULL
            )""")

    def __init__(self, guild_id, name, messagelog_channel):
        super().__init__()
        self.guild_id = guild_id
        self.name = name
        self.messagelog_channel = messagelog_channel

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildMessageLog(guild_id=result.get("guild_id"), name=result.get("name"),
                                  messagelog_channel=result.get("messagelog_channel"))
            result_list.append(obj)
        return result_list


class GuildMessageLinks(db.DatabaseTable):
    """Contains information for link scrubbing"""
    __tablename__ = 'guild_msg_links'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            role_id bigint null
            )""")

    def __init__(self, guild_id, role_id=None):
        super().__init__()
        self.guild_id = guild_id
        self.role_id = role_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildMessageLinks(guild_id=result.get("guild_id"), role_id=result.get("role_id"))
            result_list.append(obj)
        return result_list


class PunishmentTimerRecords(db.DatabaseTable):
    """Punishment Timer Records"""
    type_map = {p.type: p for p in (Mute, Deafen)}
    __tablename__ = 'punishment_timers'
    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY NOT NULL,
            guild_id bigint NOT NULL,
            actor_id bigint NOT NULL,
            target_id bigint NOT NULL,
            orig_channel_id bigint null,
            type_of_punishment bigint NOT NULL,
            reason varchar null,
            target_ts bigint NOT NULL
            )""")

    def __init__(self, guild_id, actor_id, target_id, type_of_punishment, target_ts, orig_channel_id=None, reason=None, input_id=None):
        super().__init__()
        self.id = input_id
        self.guild_id = guild_id
        self.actor_id = actor_id
        self.target_id = target_id
        self.type_of_punishment = type_of_punishment
        self.target_ts = target_ts
        self.orig_channel_id = orig_channel_id
        self.reason = reason

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = PunishmentTimerRecords(guild_id=result.get("guild_id"), actor_id=result.get("actor_id"),
                                         target_id=result.get("target_id"),
                                         type_of_punishment=result.get("type_of_punishment"),
                                         target_ts=result.get("target_ts"),
                                         orig_channel_id=result.get("orig_channel_id"), reason=result.get("reason"),
                                         input_id=result.get('id'))
            result_list.append(obj)
        return result_list


def setup(bot):
    """Adds the moderation cog to the bot."""
    bot.add_cog(Moderation(bot))
