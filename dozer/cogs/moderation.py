"""Provides moderation commands for Dozer."""
import asyncio
import datetime
import re
import time
import typing
from typing import TYPE_CHECKING, Union, Optional, Type, Set, Tuple, Dict, List

import discord
from discord import Guild, Embed, User, Member, Message, Role, PermissionOverwrite, ClientUser
from discord.ext import tasks, commands
from discord.ext.commands import BadArgument, has_permissions, RoleConverter, guild_only
from discord.utils import escape_markdown
from loguru import logger

from dozer.context import DozerContext
from ._utils import *
from .actionlogs import CustomJoinLeaveMessages, send_log, GuildNewMember
from .general import blurple
from .teams import TeamNumbers
from .. import db

if TYPE_CHECKING:
    from dozer import Dozer

__all__ = ["SafeRoleConverter", "Moderation", "NewMemPurgeConfig", "GuildNewMember"]

MAX_PURGE = 1000




class SafeRoleConverter(RoleConverter):
    """Allows for @everyone to be specified without pinging everyone"""

    async def convert(self, ctx: DozerContext, argument: str):
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

    def __init__(self, bot: "Dozer"):
        super().__init__(bot)
        self.links_config: db.ConfigCache = db.ConfigCache(GuildMessageLinks)
        self.punishment_timer_tasks: List[asyncio.Task] = []

    """=== Helper functions ==="""

    async def nm_kick_internal(self, guild: discord.Guild = None):
        """Kicks people who have not done the new member process within a set amount of time."""
        logger.debug("Starting nm_kick cycle...")
        if not guild:
            entries = await NewMemPurgeConfig.get_by()
        else:
            entries = await NewMemPurgeConfig.get_by(guild_id=guild.id)
        count: int = 0
        for entry in entries:
            guild: Guild = self.bot.get_guild(entry.guild_id)
            if guild is None:
                continue
            for mem in guild.members:
                if guild.get_role(entry.member_role) not in mem.roles:
                    delta: datetime.timedelta = datetime.datetime.now() - mem.joined_at
                    if delta.days >= entry.days:
                        await mem.kick(reason="New member purge cycle")
                        count += 1
        return count

    @discord.ext.tasks.loop(hours=168)
    async def nm_kick(self):
        """Kicks new members"""
        await self.nm_kick_internal()

    async def mod_log(self, actor: Member, action: str, target: Union[User, Member, None],
                      reason, orig_channel=None,
                      embed_color: discord.Color = discord.Color.red(), global_modlog: bool = True, duration: datetime.timedelta = None,
                      dm: bool = True, guild_override: int = None, extra_fields=None, updated_by: Member = None):
        """Generates a modlog embed"""

        if target is None:
            title = "Custom Modlog"
        else:
            title = f"User {action}!"

        modlog_embed: Embed = Embed(
            color=embed_color,
            title=title
        )
        if target is not None:
            modlog_embed.add_field(name=f"{action.capitalize()} user",
                                   value=f"{target.mention} ({target} | {target.id})", inline=False)
        modlog_embed.add_field(name="Performed by", value=f"{actor.mention} ({actor} | {actor.id})", inline=False)
        if updated_by is not None:
            modlog_embed.add_field(name="Updated by", value=f"{updated_by.mention} ({updated_by} | {updated_by.id})", inline=False)
        modlog_embed.add_field(name="Reason", value=reason or "No reason specified", inline=False)
        modlog_embed.timestamp = datetime.datetime.utcnow()
        if extra_fields is not None:
            for field in extra_fields:
                modlog_embed.add_field(name=field['name'], value=field['value'], inline=field['inline'])
        if duration:
            modlog_embed.add_field(name="Duration", value=duration)
            modlog_embed.add_field(name="Expiration", value=f"<t:{round((datetime.datetime.now() + duration).timestamp())}:R>")
        if target is not None and dm:
            try:
                # Add source guild after Preformed by to embed if the modlog is being sent to a DM
                modlog_embed.insert_field_at(2, name="Source Guild", value=f"**{actor.guild.name}** ({actor.guild.id})")
                await target.send(embed=modlog_embed)
                # Remove the source guild line from the embed
            except discord.Forbidden:
                await orig_channel.send("Failed to DM modlog to user")
            finally:
                modlog_embed.remove_field(2)
        modlog_channel: List[GuildModLog] = await GuildModLog.get_by(guild_id=actor.guild.id) if guild_override is None else \
            await GuildModLog.get_by(guild_id=guild_override)
        if orig_channel is not None:
            await orig_channel.send(embed=modlog_embed)
        if len(modlog_channel) != 0:
            if global_modlog:
                channel = self.bot.get_guild(actor.guild.id if guild_override is None else guild_override). \
                    get_channel(modlog_channel[0].modlog_channel)
                if channel is not None and channel != orig_channel:  # prevent duplicate embeds
                    try:
                        await channel.send(embed=modlog_embed)
                    except discord.Forbidden as e:
                        logger.warning(
                            f"Unable to send modlog in guild \"{channel.guild}\" ({channel.guild.id}) reason {e}")
        else:
            if orig_channel is not None:
                await orig_channel.send("Please configure modlog channel to enable modlog functionality")

    @staticmethod
    async def perm_override(member: Member, **overwrites):
        """Applies the given overrides to the given member in their guild."""
        for channel in member.guild.channels:

            overwrite: PermissionOverwrite = channel.overwrites_for(member)
            if channel.permissions_for(member.guild.me).manage_roles:
                overwrite.update(**overwrites)
                try:
                    await channel.set_permissions(target=member, overwrite=None if overwrite.is_empty() else overwrite)
                except discord.Forbidden as e:
                    logger.error(
                        f"Failed to catch missing perms in {channel} ({channel.id}) Guild: {channel.guild.id}; Error: {e}")

    hm_regex: re.Pattern = re.compile(
        r"((?P<years>\d+)y)?((?P<months>\d+)M)?((?P<weeks>\d+)w)?((?P<days>\d+)d)?((?P<hours>\d+)h)?((?P<minutes>\d+)m)?(("
        r"?P<seconds>\d+)s)?")

    def hm_to_seconds(self, hm_str: str) -> int:
        """Converts an hour-minute string to seconds. For example, '1h15m' returns 4500"""
        matches: Dict[str, str] = re.match(self.hm_regex, hm_str).groupdict()
        years: int = int(matches.get('years') or 0)
        months: int = int(matches.get('months') or 0)
        weeks: int = int(matches.get('weeks') or 0)
        days: int = int(matches.get('days') or 0)
        hours: int = int(matches.get('hours') or 0)
        minutes: int = int(matches.get('minutes') or 0)
        seconds: int = int(matches.get('seconds') or 0)
        val: int = int((years * 3.154e+7) + (months * 2.628e+6) + (weeks * 604800) + (days * 86400) + (hours * 3600) + (minutes * 60) + seconds)
        # Make sure it is a positive number, and it doesn't exceed the max 32-bit int
        # Wait so dozer is going to die at 03:14:07 on Tuesday, 19 January 2038, well I guess that's someone else's problem.
        # (yes right now its probably because of a discord non-compatibility, but once they support it we should probably fix it)
        return max(0, min(2147483647, val))

    async def start_punishment_timers(self):
        """Starts all punishment timers"""
        q: List[PunishmentTimerRecords] = await PunishmentTimerRecords.get_by()  # no filters: all
        for r in q:
            guild: Guild = self.bot.get_guild(r.guild_id)
            actor: Member = guild.get_member(r.actor_id)
            target: Member = guild.get_member(r.target_id)
            orig_channel: discord.TextChannel = self.bot.get_channel(r.orig_channel_id)
            punishment_type: int = r.type_of_punishment
            reason: str = r.reason or ""
            seconds = int(max(r.target_ts - time.time(), 0.01))
            await PunishmentTimerRecords.delete(id=r.id)
            self.bot.loop.create_task(
                self.punishment_timer(seconds, target, PunishmentTimerRecords.type_map[punishment_type], reason, actor,
                                      orig_channel))
            logger.info(
                f"Restarted {PunishmentTimerRecords.type_map[punishment_type].__name__} of {target} in {guild}")

    async def restart_all_timers(self):
        """Restarts all timers"""
        logger.info("Restarting all timers")
        for timer in self.punishment_timer_tasks:
            timer: asyncio.Task
            logger.info(f"Stopping \"{timer.get_name()}\"")
        for timer in self.punishment_timer_tasks:
            timer.cancel()
        self.punishment_timer_tasks = []
        await self.start_punishment_timers()

    async def punishment_timer(self, seconds: int, target: Member, punishment: Type[Union["Deafen", "Mute"]], reason: str,
                               actor: Member, orig_channel=None,
                               global_modlog: bool = True):
        """Asynchronous task that sleeps for a set time to unmute/undeafen a member for a set period of time."""

        # Add this task to the list of active timer tasks
        asyncio.current_task().set_name(f"PunishmentTimer for {target}")
        self.punishment_timer_tasks.append(asyncio.current_task())

        logger.info(f"Starting{' self' if not global_modlog else ''} {punishment.__name__} timer of \"{target}\" in \"{target.guild}\" will "
                    f"expire in {seconds} seconds")

        if seconds == 0:
            return

        # register the timer
        ent: PunishmentTimerRecords = PunishmentTimerRecords(
            guild_id=target.guild.id,
            actor_id=actor.id,
            target_id=target.id,
            orig_channel_id=orig_channel.id if orig_channel else 0,
            type_of_punishment=punishment.type,
            reason=reason,
            target_ts=int(seconds + time.time()),
            self_inflicted=not global_modlog
        )
        await ent.update_or_add()

        await asyncio.sleep(seconds)

        user: List[Union[Deafen, Mute]] = await punishment.get_by(member_id=target.id)
        if len(user) != 0:
            await self.mod_log(actor=actor,
                               action="un" + punishment.past_participle,
                               target=target,
                               reason=reason,
                               orig_channel=orig_channel,
                               embed_color=discord.Color.green(),
                               global_modlog=global_modlog)

            self.punishment_timer_tasks.remove(asyncio.current_task())
            self.bot.loop.create_task(coro=punishment.finished_callback(self, target))
        if ent:
            await PunishmentTimerRecords.delete(guild_id=target.guild.id, target_id=target.id,
                                                type_of_punishment=punishment.type)

    @staticmethod
    async def _check_links_warn(msg: Message, role: Role):
        """Warns a user that they can't send links."""
        warn_msg: Message = await msg.channel.send(f"{msg.author.mention}, you need the `{role.name}` role to post links!")
        await asyncio.sleep(3)
        await warn_msg.delete()

    async def check_links(self, msg: Message):
        """Checks messages for the links role if necessary, then checks if the author is allowed to send links in the server"""
        if msg.guild is None or not isinstance(msg.author,
                                               Member) or not msg.guild.me.guild_permissions.manage_messages:
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

    async def run_cross_ban(self, ctx: DozerContext, user: User, reason: str) -> List[Guild]:
        """Checks for guilds that are subscribed to the banned members guild"""
        subscriptions: List[CrossBanSubscriptions] = await CrossBanSubscriptions.get_by(subscription_id=ctx.guild.id)
        bans: List[Guild] = []
        for subscription in subscriptions:
            sub_guild: Guild = self.bot.get_guild(subscription.subscriber_id)
            if sub_guild:
                modlog_channel: List[GuildModLog] = await GuildModLog.get_by(guild_id=sub_guild.id)
                try:
                    await sub_guild.ban(user, reason=f"User Cross Banned from \"{ctx.guild}\" for: {reason}")
                    if modlog_channel:
                        await self.mod_log(actor=ctx.message.author, action="crossbanned", target=user, reason=reason,
                                           dm=False,
                                           guild_override=sub_guild.id,
                                           extra_fields=[
                                               {"name": "Origin Guild", "value": f"**{ctx.guild}** ({ctx.guild.id})",
                                                "inline": False}])
                except discord.Forbidden:
                    continue

                bans.append(sub_guild)

        return bans

    """=== context-free backend functions ==="""

    async def _mute(self, member: Member, reason: str = "No reason provided", seconds: int = 0,
                    actor: Member = None, orig_channel=None):
        """Mutes a user.
        member: the member to be muted
        reason: a reason string without a time specifier
        seconds: a duration of time for the mute to be applied. If 0, then the mute is indefinite. Do not set negative durations.
        actor: the acting user who requested the mute
        orig_channel: the channel of the request origin
        """
        results = await Mute.get_by(guild_id=member.guild.id, member_id=member.id)
        if results:
            await PunishmentTimerRecords.delete(target_id=member.id, guild_id=member.guild.id, type_of_punishment=Mute.type)
            await self.restart_all_timers()
            self.bot.loop.create_task(
                self.punishment_timer(seconds, member, Mute, reason, actor or member.guild.me, orig_channel=orig_channel))
            return False  # member already muted, edit preexisting record
        else:
            user = Mute(member_id=member.id, guild_id=member.guild.id)
            await user.update_or_add()
            await self.perm_override(member, send_messages=False, add_reactions=False, speak=False, stream=False)

            self.bot.loop.create_task(
                self.punishment_timer(seconds, member, Mute, reason, actor or member.guild.me,
                                      orig_channel=orig_channel))
            return True

    async def _unmute(self, member: Member):
        """Unmutes a user."""
        results = await Mute.get_by(guild_id=member.guild.id, member_id=member.id)
        if results:
            await Mute.delete(member_id=member.id, guild_id=member.guild.id)
            await PunishmentTimerRecords.delete(target_id=member.id, guild_id=member.guild.id,
                                                type_of_punishment=Mute.type)
            await self.perm_override(member, send_messages=None, add_reactions=None, speak=None)
            await self.restart_all_timers()
            return True
        else:
            return False  # member not muted

    async def _deafen(self, member: Member, reason: str = "No reason provided", seconds: int = 0,
                      self_inflicted: bool = False, actor=None,
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
            await PunishmentTimerRecords.delete(target_id=member.id, guild_id=member.guild.id, type_of_punishment=Deafen.type)

            await self.restart_all_timers()
            self.bot.loop.create_task(
                self.punishment_timer(seconds, member,
                                      Deafen,
                                      reason,
                                      actor or member.guild.me,
                                      orig_channel=orig_channel,
                                      global_modlog=not self_inflicted))
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

    async def _undeafen(self, member: Member):
        """Undeafens a user."""
        results = await Deafen.get_by(guild_id=member.guild.id, member_id=member.id)
        if results:
            await self.perm_override(member=member, read_messages=None)
            await PunishmentTimerRecords.delete(target_id=member.id, guild_id=member.guild.id,
                                                type_of_punishment=Deafen.type)
            await self.restart_all_timers()
            await Deafen.delete(member_id=member.id, guild_id=member.guild.id)
            truths = [True, results[0].self_inflicted]
            return truths
        else:
            return [False]

    """=== Event handlers ==="""

    @Cog.listener('on_ready')
    async def on_ready(self):
        """Restore punishment timers on bot startup and trigger the nm purge cycle"""
        await self.start_punishment_timers()
        await self.nm_kick.start()

    @Cog.listener('on_member_join')
    async def on_member_join(self, member: Member):
        """Logs that a member joined."""
        users = await Mute.get_by(guild_id=member.guild.id, member_id=member.id)
        if users:
            await self.perm_override(member, add_reactions=False, send_messages=False)
        users = await Deafen.get_by(guild_id=member.guild.id, member_id=member.id)
        if users:
            await self.perm_override(member, read_messages=False)

    @Cog.listener('on_message')
    async def on_message(self, message: Message):
        """Check things when messages come in."""
        if message.author.bot or message.guild is None or not message.guild.me.guild_permissions.manage_roles:
            return
        if await self.check_links(message):
            return
        config = await GuildNewMember.get_by(guild_id=message.guild.id)
        ctx = await self.bot.get_context(message)
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
            if config.require_team:
                teams = await TeamNumbers.get_by(user_id=message.author.id)
                if len(teams) == 0:
                    if ctx.prefix is None:
                        ctx.prefix = self.bot.config['prefix']
                    await message.reply(f"You must set a team number first. ex: `{ctx.prefix}setteam frc 0`")
                    return

            custom_log_config = await CustomJoinLeaveMessages.get_by(guild_id=message.guild.id)

            await message.author.add_roles(message.guild.get_role(role_id))
            if custom_log_config[0].send_on_verify:
                await send_log(member=message.author)

    @Cog.listener('on_message_edit')
    async def on_message_edit(self, before: Message, after: Message):
        """Checks for links"""
        await self.check_links(after)

    """=== Direct moderation commands ==="""

    @command()
    @has_permissions(kick_members=True)
    async def warn(self, ctx: DozerContext, member: Member, *, reason: str):
        """Sends a message to the mod log specifying the member has been warned without punishment."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        await self.mod_log(actor=ctx.author, action="warned", target=member, orig_channel=orig_channel, reason=reason)

    warn.example_usage = """
    `{prefix}`warn @user reason - warns a user for "reason"
    """

    @command()
    @has_permissions(kick_members=True)
    async def customlog(self, ctx: DozerContext, *, reason: str):
        """Sends a message to the mod log with custom text."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        await self.mod_log(actor=ctx.author, action="", target=None, orig_channel=orig_channel, reason=reason,
                           embed_color=discord.Color(0xFFC400))

    customlog.example_usage = """
    `{prefix}`customlog reason - warns a user for "reason"
    """

    @command()
    @has_permissions(manage_permissions=True)
    @bot_has_permissions(manage_permissions=True)
    async def timeout(self, ctx: DozerContext, duration: float):
        """Set a timeout (no sending messages or adding reactions) on the current channel."""
        results: List[MemberRole] = await MemberRole.get_by(guild_id=ctx.guild.id)
        settings: MemberRole
        if len(results) == 0:
            settings = MemberRole(guild_id=ctx.guild.id, member_role=MemberRole.nullify)
            await settings.update_or_add()
        else:
            settings = results[0]
        # None-safe - nonexistent or non-configured role return None
        member_role = ctx.guild.get_role(settings.member_role)
        if member_role is not None:
            targets = {member_role}
        else:
            await ctx.send(
                '{0.author.mention}, the members role has not been configured. This may not work as expected. Use '
                '`{0.prefix}help memberconfig` to see how to set this up.'.format(
                    ctx))
            targets: Set[Role] = set(sorted(ctx.guild.roles)[:ctx.author.top_role.position])

        to_restore: List[Tuple[Union[Role, ClientUser, Member], PermissionOverwrite]] = \
            [(target, ctx.channel.overwrites_for(target)) for target in targets]
        for target, overwrite in to_restore:
            new_overwrite: discord.PermissionOverwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages=False, add_reactions=False)
            await ctx.channel.set_permissions(target, overwrite=new_overwrite)

        for allow_target in (ctx.me, ctx.author):
            overwrite = ctx.channel.overwrites_for(allow_target)
            new_overwrite: discord.PermissionOverwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages=True)
            await ctx.channel.set_permissions(allow_target, overwrite=new_overwrite)
            to_restore.append((allow_target, overwrite))

        e: Embed = Embed(title='Timeout - {}s'.format(duration), description='This channel has been timed out.',
                          color=discord.Color.blue())
        e.set_author(name=escape_markdown(ctx.author.display_name), icon_url=ctx.author.display_avatar.replace(format='png', size=32))
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
    async def prune(self, ctx: DozerContext, target: typing.Optional[Member], num: int):
        """Bulk delete a set number of messages from the current channel."""
        await ctx.defer()

        def check_target(message: Message) -> bool:
            if target is None:
                return True
            else:
                return message.author == target

        try:
            msg: Message = await ctx.message.channel.fetch_message(num)
            deleted: List[Message] = await ctx.message.channel.purge(after=msg, limit=MAX_PURGE, check=check_target)
            await ctx.send(
                f"Deleted {len(deleted)} messages under request of {ctx.message.author.mention}",
                delete_after=5)
        except discord.NotFound:
            if num > MAX_PURGE:
                await ctx.send("Message cannot be found or you're trying to purge too many messages.")
                return
            deleted: List[Message] = await ctx.message.channel.purge(limit=num + 1, check=check_target)
            await ctx.send(
                f"Deleted {len(deleted) - 1} messages under request of {ctx.message.author.mention}",
                delete_after=5)

    prune.example_usage = """
    `{prefix}prune 10` - Delete the last 10 messages in the current channel.
    `{prefix}prune 786324930378727484` - Deletes all messages up to that message ID
    """

    @command()
    @guild_only()
    @has_permissions(manage_roles=True)
    async def punishments(self, ctx: DozerContext):
        """List currently active mutes and deafens in a guild"""
        punishments: List[PunishmentTimerRecords] = await PunishmentTimerRecords.get_by(guild_id=ctx.guild.id)
        deafen_records: List[Deafen] = await Deafen.get_by(guild_id=ctx.guild.id)
        self_inflicted: List[int] = [record.member_id for record in deafen_records if record.self_inflicted]
        deafens: List[PunishmentTimerRecords] = [punishment for punishment in punishments if
                                                 punishment.type_of_punishment == 2 and punishment.target_id not in self_inflicted]
        self_deafens: List[PunishmentTimerRecords] = [punishment for punishment in punishments if
                                                      punishment.type_of_punishment == 2 and punishment.target_id in self_inflicted]
        mutes: List[PunishmentTimerRecords] = [punishment for punishment in punishments if punishment.type_of_punishment == 1]
        embed: Embed = Embed(title=f"Active punishments in {ctx.guild}", color=blurple)
        embed.set_footer(text='Triggered by ' + ctx.author.display_name)

        def get_mention(target_id: int) -> str:
            member: Member = ctx.guild.get_member(target_id)
            if member:
                return member.mention
            else:
                return "**Member left**"

        def get_name(target_id) -> str:
            user: User = ctx.bot.get_user(target_id)
            if user:
                return str(user)
            else:
                return "**Unknown#NONE**"

        for field_number, punishments in enumerate(chunk(deafens, 3)):
            embed.add_field(name=f"Deafens - {len(deafens)}", value='\n-\n'.join(
                f"{get_mention(punishment.target_id)} ({get_name(punishment.target_id)} | {punishment.target_id}) "
                f"\nExpires: <t:{round(punishment.target_ts)}:R> Reason: {punishment.reason}"
                for punishment in punishments) or 'None', inline=False)

        for field_number, punishments in enumerate(chunk(mutes, 3)):
            embed.add_field(name=f"Mutes - {len(mutes)}", value='\n-\n'.join(
                f"{get_mention(punishment.target_id)} ({get_name(punishment.target_id)} | {punishment.target_id}) "
                f"\nExpires: <t:{round(punishment.target_ts)}:R> Reason: {punishment.reason}"
                for punishment in punishments) or 'None', inline=False)

        for field_number, punishments in enumerate(chunk(self_deafens, 3)):
            embed.add_field(name=f"Self Deafens - {len(self_deafens)}", value='\n-\n'.join(
                f"{get_mention(punishment.target_id)} ({get_name(punishment.target_id)} | {punishment.target_id}) "
                f"\nExpires: <t:{round(punishment.target_ts)}:R> Reason: {punishment.reason}"
                for punishment in punishments) or 'None', inline=False)

        await ctx.send(embed=embed)

    punishments.example_usage = """
    `{prefix}punishments:` Lists currently active punishments in current guild
    """

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def ban(self, ctx: DozerContext, user_mention: User, *, reason: str = "No reason provided"):
        """Bans the user mentioned."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        await self.mod_log(actor=ctx.author, action="banned", target=user_mention, reason=reason,
                           orig_channel=orig_channel, dm=False)
        cross_guilds = await self.run_cross_ban(ctx, user_mention, reason)
        extra_fields = [{"name": "Origin Guild", "value": f"**{ctx.guild}** ({ctx.guild.id})", "inline": False}]
        for field_number, guilds in enumerate(chunk(cross_guilds, 10)):
            extra_fields.append(
                {"name": "Cross Banned From", "value": '\n'.join(f"**{guild}** ({guild.id})" for guild in guilds),
                 "inline": False})
        await self.mod_log(actor=ctx.author, action="banned", target=user_mention, reason=reason, global_modlog=False,
                           extra_fields=extra_fields)
        await ctx.guild.ban(user_mention, reason=reason)

    ban.example_usage = """
    `{prefix}ban @user reason - ban @user for a given (optional) reason
    """

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def unban(self, ctx: DozerContext, user_mention: User, *, reason: str = "No reason provided"):
        """Unbans the user mentioned."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        await ctx.guild.unban(user_mention, reason=reason)
        await self.mod_log(actor=ctx.author, action="unbanned", target=user_mention, reason=reason,
                           orig_channel=orig_channel, embed_color=discord.Color.green())

    unban.example_usage = """
    `{prefix}unban user_id reason - unban the user corresponding to the ID for a given (optional) reason
    """

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(kick_members=True)
    async def kick(self, ctx: DozerContext, user_mention: User, *, reason: str = "No reason provided"):
        """Kicks the user mentioned."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        await self.mod_log(actor=ctx.author, action="kicked", target=user_mention, reason=reason,
                           orig_channel=orig_channel)
        await ctx.guild.kick(user_mention, reason=reason)

    kick.example_usage = """
    `{prefix}kick @user reason - kick @user for a given (optional) reason
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_permissions=True)
    async def mute(self, ctx: DozerContext, member_mentions: Member, *, reason: str = "No reason provided"):
        """Mute a user to prevent them from sending messages"""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub("", reason) or "No reason provided"
            if await self._mute(member_mentions, reason=reason, seconds=seconds, actor=ctx.author,
                                orig_channel=ctx.channel):
                await self.mod_log(ctx.author, "muted", member_mentions, reason, orig_channel, discord.Color.red(),
                                   duration=datetime.timedelta(seconds=seconds))
            else:
                await ctx.send("Member was already muted! Updating duration and reason.")
                await self.mod_log(ctx.author, "muted", member_mentions, reason, orig_channel, discord.Color.red(),
                                   duration=datetime.timedelta(seconds=seconds), global_modlog=False, dm=False)

    mute.example_usage = """
    `{prefix}mute @user 1h reason` - mute @user for 1 hour for a given reason, the timing component (1h) and reason is optional.
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_permissions=True)
    async def unmute(self, ctx: DozerContext, member_mentions: Member, *, reason="No reason provided"):
        """Unmute a user to allow them to send messages again."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        async with ctx.typing():
            if await self._unmute(member_mentions):
                await self.mod_log(actor=ctx.author, action="unmuted", target=member_mentions, reason=reason,
                                   orig_channel=orig_channel, embed_color=discord.Color.green())
            else:
                await ctx.send("Member is not muted!")

    unmute.example_usage = """
    `{prefix}unmute @user reason - unmute @user for a given (optional) reason
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_permissions=True)
    async def deafen(self, ctx: DozerContext, member_mentions: Member, *, reason: str = "No reason provided"):
        """Deafen a user to prevent them from both sending messages but also reading messages."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub("", reason) or "No reason provided"
            if await self._deafen(member_mentions, reason, seconds=seconds, self_inflicted=False, actor=ctx.author,
                                  orig_channel=orig_channel):
                await self.mod_log(actor=ctx.author, action="deafened", target=member_mentions, reason=reason,
                                   orig_channel=orig_channel,
                                   embed_color=discord.Color.red(), duration=datetime.timedelta(seconds=seconds))
            else:
                await ctx.send("Member was already deafened! Updating duration and reason.")
                await self.mod_log(ctx.author, "deafened", member_mentions, reason, orig_channel, discord.Color.red(),
                                   duration=datetime.timedelta(seconds=seconds), global_modlog=False, dm=False)

    deafen.example_usage = """
    `{prefix}deafen @user 1h reason` - deafen @user for 1 hour for a given reason, the timing component (1h) is optional.
    """

    @command()
    @bot_has_permissions(manage_permissions=True)  # Once instance globally, don't wait instead throw exception
    @discord.ext.commands.max_concurrency(1, wait=False, per=discord.ext.commands.BucketType.default)
    @discord.ext.commands.cooldown(rate=10, per=2,
                                   type=discord.ext.commands.BucketType.guild)  # 10 seconds per 2 members in the guild
    async def selfdeafen(self, ctx: DozerContext, *, reason: str = "No reason provided"):
        """Deafen yourself for a given time period to prevent you from reading or sending messages."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub("", reason) or "No reason provided"
            if seconds < 300:
                raise BadArgument("You must self deafen yourself for at least 5 minutes!")
            if await self._deafen(ctx.author, reason, seconds=seconds, self_inflicted=True, actor=ctx.author,
                                  orig_channel=orig_channel):
                await self.mod_log(ctx.author, "deafened", ctx.author, reason, orig_channel, discord.Color.red(),
                                   global_modlog=False,
                                   duration=datetime.timedelta(seconds=seconds))
            else:
                await ctx.send("You are already deafened!")

    selfdeafen.example_usage = """
    `{prefix}selfdeafen time (1h5m, both optional) reason`: deafens you if you need to get work done
    """

    @command()
    @has_permissions(manage_roles=True)
    @bot_has_permissions(manage_permissions=True)
    async def undeafen(self, ctx: DozerContext, member_mentions: Member, *, reason: str = "No reason provided"):
        """Undeafen a user to allow them to see message and send message again."""
        orig_channel = ctx.interaction.followup if ctx.interaction else ctx.channel
        async with ctx.typing():
            result = await self._undeafen(member_mentions)
            if result[0]:
                await self.mod_log(actor=ctx.author, action="undeafened", target=member_mentions, reason=reason,
                                   orig_channel=orig_channel, embed_color=discord.Color.green(),
                                   global_modlog=not result[1])
            else:
                await ctx.send("Member is not deafened!")

    undeafen.example_usage = """
    `{prefix}undeafen @user reason - undeafen @user for a given (optional) reason
    """

    @command()
    async def voicekick(self, ctx: DozerContext, member: Member, reason: str = "No reason provided"):
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
    async def purgenm(self, ctx: DozerContext):
        """Manually run a new member purge"""
        memcount = await self.nm_kick_internal(guild=ctx.guild)
        await ctx.send(f"Kicked {memcount} members due to inactivity!")

    """=== Configuration commands ==="""

    @command()
    @has_permissions(administrator=True)
    async def modlogconfig(self, ctx: DozerContext, channel_mentions: discord.TextChannel):
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
    @has_permissions(manage_guild=True)
    async def verifymember(self, ctx, member: Member):
        """Command to verify a member who may not have a team number set, or who hasn't sent the required
        verification message. """
        config = await GuildNewMember.get_by(guild_id=ctx.guild.id)
        if len(config) != 0:
            role_id = config[0].role_id
            role = ctx.guild.get_role(role_id)
            if role in member.roles:
                await ctx.send("Member is already verified. ")
                return

            await member.add_roles(role)

            custom_join_config = await CustomJoinLeaveMessages.get_by(guild_id=member.guild.id)
            if custom_join_config[0].send_on_verify:
                await send_log(member=member)
            await ctx.send(f"Member verified on request of {ctx.author.display_name}")

    @command()
    @has_permissions(administrator=True)
    async def nmconfig(self, ctx: DozerContext, channel_mention: discord.TextChannel, role: Role, *, message,
                       requireteam=None):
        """Sets the config for the new members channel"""
        config = await GuildNewMember.get_by(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.channel_id = channel_mention.id
            config.role_id = role.id
            config.require_team = requireteam
            config.message = message.casefold()

        else:
            config = GuildNewMember(guild_id=ctx.guild.id, channel_id=channel_mention.id, role_id=role.id,
                                    message=message.casefold(), require_team=requireteam)
        await config.update_or_add()

        role_name = role.name
        await ctx.send(
            "New Member Channel configured as: {channel}. Role configured as: {role}. Team numbers required: "
            "{required}. Message: {message}".format(
                channel=channel_mention.name, role=role_name, required=requireteam, message=message))

    nmconfig.example_usage = """
    `{prefix}nmconfig #new_members Member I have read the rules and regulations` - Configures the #new_members channel 
    so if someone types "I have read the rules and regulations" it assigns them the Member role. 
    """

    @command()
    @has_permissions(administrator=True)
    async def nmpurgeconfig(self, ctx: DozerContext, role: Role, days: int):
        """Sets the config for the new members purge"""
        config = NewMemPurgeConfig(guild_id=ctx.guild.id, member_role=role.id, days=days)
        await config.update_or_add()

        await ctx.send("Settings saved!")

    nmpurgeconfig.example_usage = """
    `{prefix}nmpurgeconfig Members 90: Kicks everyone who doesn't have the members role 90 days after they join.
    """

    @command()
    @has_permissions(administrator=True)
    async def memberconfig(self, ctx: DozerContext, *, member_role: Role):
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
    async def linkscrubconfig(self, ctx: DozerContext, *, link_role: Role):
        """
        Set a role that users must have in order to post links.
        This accepts the safe default role conventions that the memberconfig command does.
        """
        if link_role >= ctx.author.top_role:
            raise BadArgument('Link role cannot be higher than your top role!')
        settings: GuildMessageLinks
        results: List[GuildMessageLinks] = await GuildMessageLinks.get_by(guild_id=ctx.guild.id)
        if len(results) == 0:
            settings = GuildMessageLinks(guild_id=ctx.guild.id, role_id=link_role.id)
        else:
            settings = results[0]
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

    @group(invoke_without_command=True)
    @has_permissions(manage_messages=True)
    async def crossbans(self, ctx: DozerContext):
        """Cross ban"""
        subscriptions = await CrossBanSubscriptions.get_by(subscriber_id=ctx.guild.id)
        subscribers = await CrossBanSubscriptions.get_by(subscription_id=ctx.guild.id)
        embed = Embed(title="Cross ban subscriptions", color=blurple)
        for field_number, target_ids in enumerate(chunk(subscriptions, 10)):
            embed.add_field(name='Subscriptions',
                            value='\n'.join(f"{self.bot.get_guild(sub_id.subscription_id)} | {sub_id.subscription_id}"
                                            for sub_id in target_ids) or 'None', inline=False)
        for field_number, target_ids in enumerate(chunk(subscribers, 10)):
            embed.add_field(name='Subscribers',
                            value='\n'.join(f"{self.bot.get_guild(sub_id.subscriber_id)} | {sub_id.subscriber_id}"
                                            for sub_id in target_ids) or 'None', inline=False)
        embed.set_footer(text='Triggered by ' + ctx.author.display_name)

        await ctx.send(embed=embed)

    @crossbans.command()
    @has_permissions(manage_messages=True)
    async def view_subs(self, ctx: DozerContext):
        """View crossban subscriptions for the current server"""
        await self.crossbans(ctx)

    @crossbans.command()
    @has_permissions(administrator=True)
    @bot_has_permissions(ban_members=True)
    async def subscribe(self, ctx: DozerContext, guild_id: str):
        """Subscribe to a guild to cross ban from"""
        guild_id: int = int(guild_id)
        guild = self.bot.get_guild(guild_id)
        if guild:
            subscription: CrossBanSubscriptions = CrossBanSubscriptions(
                subscriber_id=ctx.guild.id,
                subscription_id=guild.id
            )
            await subscription.update_or_add()
            embed: Embed = Embed(title='Success!',
                                 description=f"**{ctx.guild}** is now subscribed to receive crossbans from **{guild}**",
                                 color=blurple)
            embed.set_footer(text='Triggered by ' + ctx.author.display_name)
            await ctx.send(embed=embed)
        else:
            raise BadArgument("Dozer could not find that guild! Make sure that dozer is in that guild!")

    @crossbans.command()
    @has_permissions(administrator=True)
    async def unsubscribe(self, ctx: DozerContext, guild_id):
        """Remove cross ban subscription"""
        guild_id = int(guild_id)
        result = await CrossBanSubscriptions.delete(
            subscriber_id=ctx.guild.id,
            subscription_id=guild_id
        )

        if int(result.split(" ", 1)[1]) > 0:
            guild: Guild = self.bot.get_guild(guild_id)
            embed = Embed(title='Success!',
                          description=f"**{ctx.guild}** is no longer subscribed to receive crossbans from **{guild}**",
                          color=blurple)
            embed.set_footer(text='Triggered by ' + ctx.author.display_name)
            await ctx.send(embed=embed)
        else:
            raise BadArgument("Dozer could not find a subscription to that guild!")


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

    def __init__(self, member_id: int, guild_id: int):
        super().__init__()
        self.member_id: int = member_id
        self.guild_id: int = guild_id

    @classmethod
    async def get_by(cls, **kwargs) -> List["Mute"]:
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

    def __init__(self, member_id: int, guild_id: int, self_inflicted: bool):
        super().__init__()
        self.member_id: int = member_id
        self.guild_id: int = guild_id
        self.self_inflicted: bool = self_inflicted

    @classmethod
    async def get_by(cls, **kwargs) -> List["Deafen"]:
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

    def __init__(self, guild_id: int, modlog_channel: int, name: str):
        super().__init__()
        self.guild_id: int = guild_id
        self.modlog_channel: int = modlog_channel
        self.name: str = name

    @classmethod
    async def get_by(cls, **kwargs) -> List["GuildModLog"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildModLog(guild_id=result.get("guild_id"), modlog_channel=result.get("modlog_channel"),
                              name=result.get("name"))
            result_list.append(obj)
        return result_list


class CrossBanSubscriptions(db.DatabaseTable):
    """Holds all cross ban subscriptions"""
    __tablename__ = 'cross_ban_subscriptions'
    __uniques__ = 'subscriber_id, subscription_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__}(
                subscriber_id bigint NOT NULL,
                subscription_id bigint NOT NULL,
                UNIQUE (subscriber_id, subscription_id)
            )""")

    def __init__(self, subscriber_id: int, subscription_id: int):
        self.subscriber_id: int = subscriber_id
        self.subscription_id: int = subscription_id

    @classmethod
    async def get_by(cls, **kwargs) -> List["CrossBanSubscriptions"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = CrossBanSubscriptions(subscriber_id=result.get("subscriber_id"),
                                        subscription_id=result.get("subscription_id"))
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

    def __init__(self, guild_id: int, member_role: int = None):
        super().__init__()
        self.guild_id: int = guild_id
        self.member_role: int = member_role

    @classmethod
    async def get_by(cls, **kwargs) -> List["MemberRole"]:
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

    def __init__(self, guild_id: int, member_role: int, days: int):
        super().__init__()
        self.guild_id: int = guild_id
        self.member_role: int = member_role
        self.days: int = days

    @classmethod
    async def get_by(cls, **kwargs) -> List["NewMemPurgeConfig"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = NewMemPurgeConfig(member_role=result.get("member_role"),
                                    guild_id=result.get("guild_id"),
                                    days=result.get("days"))
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

    def __init__(self, guild_id: int, role_id: int = None):
        super().__init__()
        self.guild_id: int = guild_id
        self.role_id: int = role_id

    @classmethod
    async def get_by(cls, **kwargs) -> List["GuildMessageLinks"]:
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

    def __init__(self, guild_id: int, actor_id: int, target_id: int, type_of_punishment: int, target_ts: int,
                 orig_channel_id: int = None, reason: Optional[str] = None, input_id: int = None, self_inflicted: bool = False):
        super().__init__()
        self.id: int = input_id
        self.guild_id: int = guild_id
        self.actor_id: int = actor_id
        self.target_id: int = target_id
        self.type_of_punishment: int = type_of_punishment
        self.target_ts: int = target_ts
        self.orig_channel_id: Optional[int] = orig_channel_id
        self.reason: Optional[str] = reason
        self.self_inflicted: bool = self_inflicted

    @classmethod
    async def get_by(cls, **kwargs) -> List["PunishmentTimerRecords"]:
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = PunishmentTimerRecords(guild_id=result.get("guild_id"), actor_id=result.get("actor_id"),
                                         target_id=result.get("target_id"),
                                         type_of_punishment=result.get("type_of_punishment"),
                                         target_ts=result.get("target_ts"),
                                         orig_channel_id=result.get("orig_channel_id"), reason=result.get("reason"),
                                         input_id=result.get('id'), self_inflicted=result.get("self_inflicted"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            ALTER TABLE {self.__tablename__} ADD self_inflicted bool NOT NULL DEFAULT false;
            """)

    __versions__ = [version_1]


async def setup(bot):
    """Adds the moderation cog to the bot."""
    await bot.add_cog(Moderation(bot))
