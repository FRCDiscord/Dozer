"""Records members' XP and level."""

import functools
import asyncio
import itertools
import logging
import math
from datetime import timedelta, timezone, datetime
import random
import time
import aiohttp
import discord
from discord.ext.commands import guild_only, has_permissions, BadArgument
from discord.ext.tasks import loop

from ._utils import *
from .info import blurple
from .. import db

DOZER_LOGGER = logging.getLogger(__name__)


class Levels(Cog):
    """Commands and event handlers for managing levels and XP."""

    cache_size = 750

    def __init__(self, bot):
        super().__init__(bot)
        self._loop = bot.loop
        self._guild_settings = {}
        self._level_roles = {}
        self._xp_cache = {}  # dct[(guild_id, user_id)] = MemberXPCache(...)
        self._loop.create_task(self.preload_cache())
        self.session = aiohttp.ClientSession(loop=bot.loop)
        self.sync_task.start()

    @staticmethod
    @functools.lru_cache(cache_size)
    def total_xp_for_level(level):
        """Compute the total XP required to reach the given level.
        All members at this level have at least this much XP.
        """
        # https://github.com/Mee6/Mee6-documentation/blob/9d98a8fe8ab494fd85ec27750592fc9f8ef82472/docs/levels_xp.md
        # > The formula to calculate how many xp you need for the next level is 5 * (lvl ^ 2) + 50 * lvl + 100 with
        # > your current level as lvl
        needed = 0
        for lvl in range(level):
            needed += 5 * lvl ** 2 + 50 * lvl + 100
        return needed

    @staticmethod
    @functools.lru_cache(cache_size)
    def level_for_total_xp(xp):
        """Compute the level of a member with the given amount of total XP.
        All members with this much XP are at or above this level.
        """
        # https://github.com/Mee6/Mee6-documentation/blob/9d98a8fe8ab494fd85ec27750592fc9f8ef82472/docs/levels_xp.md
        # > The formula to calculate how many xp you need for the next level is 5 * (lvl ^ 2) + 50 * lvl + 100 with
        # > your current level as lvl
        lvl = 0
        while xp >= 0:
            xp -= 5 * lvl ** 2 + 50 * lvl + 100
            lvl += 1
        return lvl - 1

    async def preload_cache(self):
        """Load all guild settings from the database."""
        await self.bot.wait_until_ready()
        DOZER_LOGGER.info("Preloading guild settings")
        await self.update_server_settings_cache()
        await self.update_level_role_cache()
        DOZER_LOGGER.info(f"Loaded settings for {len(self._guild_settings)} guilds; and {len(self._level_roles)} level roles")
        # Load subset of member XP records here?

    async def update_server_settings_cache(self):
        """Updates the server settings cache from the database"""
        self._guild_settings = {}
        records = await GuildXPSettings.get_by()  # no filters, get all
        for record in records:
            self._guild_settings[record.guild_id] = record

    async def update_level_role_cache(self):
        """Updates level role cache from the database"""
        self._level_roles = {}
        level_roles = await XPRole.get_by()
        for role in level_roles:
            if self._level_roles.get(role.guild_id):
                self._level_roles[role.guild_id].append(role)
            else:
                self._level_roles[role.guild_id] = [role]

    async def check_new_roles(self, guild, member, cached_member):
        """Check and see if a member has qualified to get a new role"""
        roles = self._level_roles.get(guild.id)
        to_add = []
        if roles:
            for level_role in roles:
                if self.level_for_total_xp(cached_member.total_xp) >= level_role.level:
                    add_role = guild.get_role(level_role.role_id)
                    if add_role not in member.roles:
                        to_add.append(add_role)
            try:
                await member.add_roles(*to_add, reason="Level Up")
            except discord.Forbidden:
                DOZER_LOGGER.debug(f"Unable to add roles to {member} in guild {guild} Reason: Forbidden")

    async def check_level_up(self, guild, member, old_xp, new_xp):
        """Check and see if a member has ranked up, and then send a message if enabled"""
        old_level = self.level_for_total_xp(old_xp)
        new_level = self.level_for_total_xp(new_xp)
        if new_level > old_level:
            settings = self._guild_settings[guild.id]
            if settings.lvl_up_msgs != -1:
                channel = guild.get_channel(settings.lvl_up_msgs)
                if channel:
                    await channel.send(f"{member.mention}, you have reached level {new_level}!")

    async def _load_member(self, guild_id, member_id):
        """Check to see if a member is in the level cache and if not load from the database"""
        cached_member = self._xp_cache.get((guild_id, member_id))
        if cached_member is None:
            DOZER_LOGGER.debug("Cache miss: guild_id=%d, user_id=%d", guild_id, member_id)
            records = await MemberXP.get_by(guild_id=guild_id, user_id=member_id)
            if records:
                DOZER_LOGGER.debug("Loading from database")
                cached_member = MemberXPCache.from_record(records[0])
            else:
                DOZER_LOGGER.debug("Creating from scratch")
                cached_member = MemberXPCache(0, datetime.now(tz=timezone.utc), 0, True)
            self._xp_cache[(guild_id, member_id)] = cached_member
        return cached_member

    async def sync_to_database(self):
        """Sync dirty records to the database, and evict others from the cache."""
        # logger.info("Syncing XP to database")

        # Deleting from a dict while iterating will error, so collect the keys up front and iterate that
        # Note that all mutation of `self._xp_cache` happens before the first yield point to prevent race conditions
        keys = list(self._xp_cache.keys())
        to_write = []  # records to write to the database
        evicted = 0
        for (guild_id, user_id) in keys:
            cached_member = self._xp_cache[(guild_id, user_id)]
            if not cached_member.dirty:
                # Evict records that haven't changed since last run from cache to conserve memory
                del self._xp_cache[(guild_id, user_id)]
                evicted += 1
                continue
            to_write.append((guild_id, user_id, cached_member.total_xp, cached_member.total_messages, cached_member.last_given_at))
            cached_member.dirty = False

        if not to_write:
            DOZER_LOGGER.debug("Sync task skipped, nothing to do")
            return
        # Query written manually to insert all records at once
        async with db.Pool.acquire() as conn:
            await conn.executemany(f"INSERT INTO {MemberXP.__tablename__} (guild_id, user_id, total_xp, total_messages, last_given_at)"
                                   f" VALUES ($1, $2, $3, $4, $5) ON CONFLICT ({MemberXP.__uniques__}) DO UPDATE"
                                   f" SET total_xp = EXCLUDED.total_xp, total_messages = EXCLUDED.total_messages, last_given_at = "
                                   f"EXCLUDED.last_given_at",
                                   to_write)
        DOZER_LOGGER.debug(f"Inserted/updated {len(to_write)} record(s); Evicted {evicted} records(s)")

    @loop(minutes=2.5)
    async def sync_task(self):
        """Sync dirty records to the database, and evict others from the cache.
        This function merely wraps `sync_to_database` into a periodic task.
        """
        # @loop(...) assumes that getattr(self, func.__name__) is the task, so this needs to be a new function instead
        # of `sync_task = loop(minutes=1)(sync_to_database)`
        await self.sync_to_database()

    @sync_task.before_loop
    async def before_sync(self):
        """Do preparation work before starting the periodic timer to sync XP with the database."""
        await self.bot.wait_until_ready()

    def cog_unload(self):
        """Detach from the running bot and cancel long-running code as the cog is unloaded."""
        self.sync_task.stop()

    def _ensure_sync_running(self):
        task = self.sync_task.get_task()
        if task is None or not task.done():  # has not been started or has been started and not stopped
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            DOZER_LOGGER.warning("Task syncing records was cancelled prematurely, restarting")
        else:
            # exc could be None if the task returns normally, but that would also be an error
            DOZER_LOGGER.error("Task syncing records failed: %r", exc)
        finally:
            self.sync_task.start()

    def _fmt_member(self, guild, user_id):
        member = guild.get_member(user_id)
        if member:
            return str(member.mention)
        else:  # Still try to see if the bot can find the user to get their name
            user = self.bot.get_user(user_id)
            if user:
                return user
            else:  # If the bot can't get the user's name then return the user's id
                return f"({user_id})"

    @Cog.listener('on_message')
    async def give_message_xp(self, message):
        """Handle giving XP to a user for a message."""
        if message.author.bot or not message.guild:
            return
        guild_settings = self._guild_settings.get(message.guild.id)
        if guild_settings is None or not guild_settings.enabled:
            return

        cached_member = await self._load_member(message.guild.id, message.author.id)
        await self.check_new_roles(message.guild, message.author, cached_member)
        old_xp = cached_member.total_xp

        timestamp = message.created_at.replace(tzinfo=timezone.utc)
        if cached_member.last_given_at is None or timestamp - cached_member.last_given_at > timedelta(seconds=guild_settings.xp_cooldown):
            cached_member.total_xp += random.randint(guild_settings.xp_min, guild_settings.xp_max)
            cached_member.last_given_at = timestamp
        cached_member.total_messages += 1
        cached_member.dirty = True

        await self.check_level_up(message.guild, message.author, old_xp, cached_member.total_xp)

    @command(aliases=["mee6sync"])
    @guild_only()  # Prevent command from being executed in a DM
    @discord.ext.commands.max_concurrency(1, wait=False)  # Only allows one instance of this command to run at a time globally
    @discord.ext.commands.cooldown(rate=1, per=900, type=discord.ext.commands.BucketType.guild)  # A cooldown of 15 minutes per guild to prevent spam
    @has_permissions(administrator=True)
    async def meesyncs(self, ctx):
        """Function to scrap ranking data from the mee6 api and save it to the database"""
        guild_id = ctx.guild.id
        progress_template = "Currently syncing from Mee6 API please wait... Page: {page}"
        DOZER_LOGGER.info(f"Syncing Mee6 level data for {ctx.guild.member_count} members from guild {ctx.guild}({guild_id})")

        if self._guild_settings.get(guild_id):
            self._guild_settings[guild_id].enabled = False

        await self.sync_to_database()  # We sync the database twice so that the entire cache gets flushed
        await self.sync_to_database()  # This is to prevent cache entries from overwriting the new synced data

        msg = await ctx.send(progress_template.format(page="N/A"))
        for page in itertools.count():
            async with self.session.get(f"https://mee6.xyz/api/plugins/levels/leaderboard/{guild_id}?page={page}") as response:
                data = await response.json()
                if data.get("players") and len(data["players"]) > 0:
                    for user in data["players"]:
                        ent = MemberXP(
                            guild_id=int(guild_id),
                            user_id=int(user["id"]),
                            total_xp=int(user["xp"]),
                            total_messages=int(user["message_count"]),
                            last_given_at=ctx.message.created_at.replace(tzinfo=timezone.utc)
                        )
                        await ent.update_or_add()
                    if page % 2:
                        await msg.edit(content=progress_template.format(page=page))
                else:
                    break
            await asyncio.sleep(1.25)  # Slow down api calls as to not anger cloudflare

        await self.update_server_settings_cache()  # We refresh the settings cache to return the settings back to previous values
        await msg.edit(content="Levels data successfully synced from Mee6")
        DOZER_LOGGER.info(f"Successfully synced Mee6 data for guild {ctx.guild}({guild_id})")

    meesyncs.example_usage = """
    `{prefix}meesyncs`: Sync ranking data from the mee6 API to dozer's database
    """

    @command(aliases=["rolelevels", "levelroles"])
    @guild_only()
    async def checkrolelevels(self, ctx):
        """Displays all level associated roles"""
        roles = sorted(self._level_roles.get(ctx.guild.id), key=lambda entry: entry.level)  # Sort roles based on level
        e = discord.Embed(title=f"Level roles for {ctx.guild}", color=blurple)
        if roles:
            e.description = f"This server has {len(roles)} level roles"
            for level_role in roles.__reversed__():
                role = ctx.guild.get_role(level_role.role_id)
                if_unavailable = f"Deleted role"
                e.add_field(name=f"Level: {level_role.level}", value=rf"{role.mention if role else if_unavailable}", inline=False)
        else:
            e.description = "This server has no level roles assigned"

        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    checkrolelevels.example_usage = """
    `{prefix}checkrolelevels`: Returns an embed of all the role levels 
    """

    @group(invoke_without_command=True, aliases=["configurelevels"])
    @guild_only()
    async def configureranks(self, ctx):
        """Configures dozer ranks:tm:"""
        settings = self._guild_settings.get(ctx.guild.id)
        if settings:
            embed = discord.Embed(color=blurple)
            embed.set_footer(text='Triggered by ' + ctx.author.display_name)

            notify_channel = ctx.guild.get_channel(settings.lvl_up_msgs)

            enabled = "Enabled" if settings.enabled else "Disabled"
            embed.set_author(name=ctx.guild, icon_url=ctx.guild.icon_url)
            embed.add_field(name=f"Levels are {enabled} for {ctx.guild}", value=f"XP min: {settings.xp_min}\n"
                                                                                f"XP max: {settings.xp_max}\n"
                                                                                f"Cooldown: {settings.xp_cooldown} Seconds\n"
                                                                                f"Notification channel: {notify_channel}")
            await ctx.send(embed=embed)
        else:
            await ctx.send("Levels not configured for this server")

    configureranks.example_usage = """
    `{prefix}configureranks`: Returns current configuration
    `{prefix}configureranks xprange 5 15`: Sets the xp range
    `{prefix}configureranks setcooldown 15`: Sets the cooldown time in seconds
    `{prefix}configureranks toggle`: Toggles levels
    `{prefix}configureranks notificationchannel channel`: Sets level up message channel
    `{prefix}configureranks notificationsoff`: Turns off notification channel
    `{prefix}configureranks setrolelevel role level`: Adds a level role
    `{prefix}configureranks delrolelevel role`: Deletes a level role 
    """

    @configureranks.command(aliases=["xp"])
    @guild_only()
    @has_permissions(manage_guild=True)
    async def xprange(self, ctx, xp_min: int, xp_max: int):
        """Set the range of a servers levels random xp"""
        if xp_min > xp_max:
            raise BadArgument("XP_min cannot be greater than XP_max!")
        if xp_min < 0:
            raise BadArgument("XP_min cannot be below zero!")
        await self._cfg_guild_setting(ctx, xp_min=xp_min, xp_max=xp_max)

    @configureranks.command(aliases=["cooldown"])
    @guild_only()
    @has_permissions(manage_guild=True)
    async def setcooldown(self, ctx, cooldown: int):
        """Set the time in seconds between messages before xp is calculated again"""
        if cooldown < 0:
            raise BadArgument("Cooldown cannot be less than zero!")
        await self._cfg_guild_setting(ctx, xp_cooldown=cooldown)

    @configureranks.command()
    @guild_only()
    @has_permissions(manage_guild=True)
    async def toggle(self, ctx):
        """Toggle dozer ranks"""
        await self._cfg_guild_setting(ctx, toggle_enabled=True)

    @configureranks.command(aliases=["notifications"])
    @guild_only()
    @has_permissions(manage_guild=True)
    async def notificationchannel(self, ctx, channel: discord.TextChannel):
        """Set up the channel where level up messages are sent"""
        await self._cfg_guild_setting(ctx, lvl_up_msgs_id=channel.id)

    @configureranks.command(aliases=["nonotifications"])
    @guild_only()
    @has_permissions(manage_guild=True)
    async def notificationsoff(self, ctx):
        """Turns off level up messages"""
        await self._cfg_guild_setting(ctx, no_lvl_up=True)

    @configureranks.command(aliases=["addrolelevel", "addlevelrole", "setlevelrole"])
    @guild_only()
    @has_permissions(manage_roles=True)
    async def setrolelevel(self, ctx, role: discord.Role, level: int):
        """Sets a role to be given to a user when they reach a certain level"""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot give roles higher than your top role!')

        if role > ctx.me.top_role:
            raise BadArgument('Cannot give roles higher than my top role!')

        if level <= 0:
            raise BadArgument("Cannot give level roles lower and/or equal to zero!")

        if role == ctx.guild.default_role:
            raise BadArgument("Cannot give @\N{ZERO WIDTH SPACE}everyone for a level")

        if role.managed:
            raise BadArgument("I am not allowed to assign that role!")

        async with ctx.channel.typing():  # Send typing to show that the bot is thinking and not stalled
            ent = XPRole(
                guild_id=int(ctx.guild.id),
                role_id=int(role.id),
                level=int(level)
            )

            await ent.update_or_add()

            await self.update_level_role_cache()

            e = discord.Embed(color=blurple)
            e.add_field(name='Success!', value=f"{role.mention} will be given to users who reach level {level}")
            e.set_footer(text='Triggered by ' + ctx.author.display_name)
            await ctx.send(embed=e)

    setrolelevel.example_usage = """
    `{prefix}setrolelevel "level 2" 2`: Will configure the role "level 2" to be given to users who reach level 2` 
    """

    @configureranks.command(aliases=["delrolelevel"])
    @guild_only()
    @has_permissions(manage_roles=True)
    async def removerolelevel(self, ctx, role: discord.Role):
        """Removes a levelrole"""
        e = discord.Embed(color=blurple)
        async with ctx.channel.typing():
            removed = int((await XPRole.delete(role_id=int(role.id))).split(" ", 1)[1])
            if removed > 0:
                await self.update_level_role_cache()
                e.add_field(name='Success!', value=f"{role.mention} was removed from the levels database")
            else:
                e.add_field(name='Failed!', value=f"{role.mention} was not found in the levels database!")
            e.set_footer(text='Triggered by ' + ctx.author.display_name)
            await ctx.send(embed=e)

    removerolelevel.example_usage = """
    `{prefix}removerolelevel level 2 `: Will remove role "level 2" from level roles
    """

    async def _cfg_guild_setting(self, ctx, xp_min=None, xp_max=None, xp_cooldown=None, lvl_up_msgs_id=None, toggle_enabled=None, no_lvl_up=False):
        """Basic Database entry updater"""
        async with ctx.channel.typing():  # Send typing to show that the bot is thinking and not stalled
            results = await GuildXPSettings.get_by(guild_id=int(ctx.guild.id))

            if len(results):  # Get the old values to merge with the new ones
                old_ent = results[0]
            else:
                old_ent = GuildXPSettings(  # Create a entry containing default values
                    guild_id=int(ctx.guild.id),
                    xp_min=5,
                    xp_max=15,
                    xp_cooldown=15,
                    entropy_value=0,  # Is in table but is not used yet
                    lvl_up_msgs=-1,
                    enabled=False
                )

            ent = GuildXPSettings(
                guild_id=int(ctx.guild.id),
                xp_min=int(xp_min) if xp_min is not None else old_ent.xp_min,
                xp_max=int(xp_max) if xp_max is not None else old_ent.xp_max,
                xp_cooldown=int(xp_cooldown) if xp_cooldown is not None else old_ent.xp_cooldown,
                entropy_value=0,  # Is in table but is not used yet
                lvl_up_msgs=int(lvl_up_msgs_id) if lvl_up_msgs_id else int(old_ent.lvl_up_msgs) if not no_lvl_up else -1,
                enabled=not old_ent.enabled if toggle_enabled else old_ent.enabled
            )
            await ent.update_or_add()
            await self.update_server_settings_cache()
            lvl_up_msgs = ctx.guild.get_channel(ent.lvl_up_msgs)
            embed = discord.Embed(color=blurple)
            embed.set_author(name=ctx.guild, icon_url=ctx.guild.icon_url)
            embed.set_footer(text='Triggered by ' + ctx.author.display_name)
            enabled = "Enabled" if ent.enabled else "Disabled"
            embed.add_field(name=f"Levels are {enabled} for {ctx.guild}", value=f"XP min: {ent.xp_min}\n"
                                                                                f"XP max: {ent.xp_max}\n"
                                                                                f"Cooldown: {ent.xp_cooldown} Seconds\n"
                                                                                f"Notification channel: {lvl_up_msgs}")
            await ctx.send(embed=embed)

    @command(aliases=["rnak", "level"])
    @guild_only()
    @discord.ext.commands.cooldown(rate=1, per=5, type=discord.ext.commands.BucketType.user)
    async def rank(self, ctx, *, member: discord.Member = None):
        """Get a user's ranking on the XP leaderboard.
        If no member is passed, the caller's ranking is shown.
        """
        member = member or ctx.author
        embed = discord.Embed(color=member.color)

        guild_settings = self._guild_settings.get(ctx.message.guild.id)

        if guild_settings is None or not guild_settings.enabled:
            embed.description = "Levels are not enabled in this server"
        else:
            cache_record = await self._load_member(ctx.guild.id, member.id)

            # Make Postgres compute the rank for us (need WITH-query so rank() sees records for every user)
            db_record = await db.Pool.fetchrow(f"""
                WITH ranked_xp AS (
                    SELECT user_id, rank() OVER (ORDER BY total_xp DESC) FROM {MemberXP.__tablename__}
                    WHERE guild_id = $1
                ) SELECT rank FROM ranked_xp WHERE user_id = $2;
            """, ctx.guild.id, member.id)

            total_xp = cache_record.total_xp
            db_count = await db.Pool.fetchval(f"""SELECT count(*) FROM {MemberXP.__tablename__} WHERE guild_id = $1; """, ctx.guild.id)
            # Prevents 1/1 in servers of ~100 and 50/40 in shrunk servers
            count = ctx.guild.member_count if ctx.guild.member_count > db_count else db_count
            level = self.level_for_total_xp(total_xp)
            level_floor = self.total_xp_for_level(level)
            level_xp = self.total_xp_for_level(level + 1) - level_floor

            if db_record:
                rank = db_record.get("rank")
            else:
                rank = count

            embed.description = (f"Level {level}, {total_xp - level_floor}/{level_xp} XP to level up ({total_xp} total)\n"
                                 f"#{rank} of {count} in this server")
        embed.set_author(name=member.display_name, icon_url=member.avatar_url_as(format='png', size=64))
        await ctx.send(embed=embed)

    rank.example_usage = """
    `{prefix}rank`: show your ranking
    `{prefix}rank coolgal#1234`: show another user's ranking
    """

    @command(aliases=["ranks", "leaderboard"])
    @guild_only()
    async def levels(self, ctx):
        """Show the XP leaderboard for this server. Scoreboard refreshes every 5 minutes or so"""

        # Order by total_xp needs a tiebreaker, otherwise all records with equal XP have the same rank
        # This causes rankings like #1, #1, #1, #4, #4, #6, ...
        # user_id is arbitrary, chosen because it is guaranteed to be unique between two records in the same guild
        records = await db.Pool.fetch(f"""
            SELECT user_id, total_xp, rank() OVER (ORDER BY total_xp DESC, user_id) FROM {MemberXP.__tablename__}
            WHERE guild_id = $1 ORDER BY rank;
        """, ctx.guild.id)

        if len(records):
            embeds = []
            for page_num, page in enumerate(chunk(records, 10)):
                embed = discord.Embed(title=f"Rankings for {ctx.guild}", color=discord.Color.blue())
                embed.description = '\n'.join(f"#{rank}: {self._fmt_member(ctx.guild, user_id)}"
                                              f" (lvl {self.level_for_total_xp(total_xp)}, {total_xp} XP)"
                                              for (user_id, total_xp, rank) in page)
                embed.set_footer(text=f"Page {page_num + 1} of {math.ceil(len(records) / 10)}")
                embeds.append(embed)
            await paginate(ctx, embeds)
        else:
            embed = discord.Embed(title=f"Rankings for {ctx.guild}", color=discord.Color.red())
            embed.description = f"Rankings currently unavailable for {ctx.guild}"
            embed.set_footer(text="Please Try Again Later")
            await ctx.send(embed=embed)

    levels.example_usage = """
    `{prefix}levels`: show the XP leaderboard
    """


class XPRole(db.DatabaseTable):
    """Database table mapping a guild and user to their XP and related values."""
    __tablename__ = "roles_levels_xp"
    __uniques__ = "guild_id, role_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE {cls.__tablename__} (
                guild_id bigint NOT NULL,
                role_id bigint NOT NULL,
                level int NOT NULL,
                PRIMARY KEY (guild_id, role_id)
                )""")

    def __init__(self, guild_id, role_id, level):
        super().__init__()
        self.guild_id = guild_id
        self.role_id = role_id
        self.level = level

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = XPRole(guild_id=result.get("guild_id"), role_id=result.get("role_id"),
                         level=result.get("level"))
            result_list.append(obj)
        return result_list


class MemberXP(db.DatabaseTable):
    """Database table mapping a guild and user to their XP and related values."""
    __tablename__ = "levels_member_xp"
    __uniques__ = "guild_id, user_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL,
            user_id bigint NOT NULL,
            total_xp bigint NOT NULL,
            total_messages int NOT NULL,
            last_given_at timestamptz NOT NULL,
            PRIMARY KEY (guild_id, user_id)
            )""")

    def __init__(self, guild_id, user_id, total_xp, total_messages, last_given_at):
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.total_xp = total_xp
        self.total_messages = total_messages
        self.last_given_at = last_given_at

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = MemberXP(guild_id=result.get("guild_id"), user_id=result.get("user_id"),
                           total_xp=result.get("total_xp"), total_messages=result.get("total_messages"),
                           last_given_at=result.get("last_given_at"))
            result_list.append(obj)
        return result_list


class MemberXPCache:
    """ A cached record of a user's XP.
        This has all of the fields of `MemberXP` except the primary key, and an additional `dirty` flag that indicates
        whether the record has been changed since it was loaded from the database or created.
    """

    def __init__(self, total_xp: int, last_given_at: datetime, total_messages: int, dirty: bool):
        self.total_xp = total_xp
        self.total_messages = total_messages
        self.last_given_at = last_given_at
        self.dirty = dirty

    def __repr__(self):
        return f"<MemberXPCache total_xp={self.total_xp!r} last_given_at={self.last_given_at!r} total_messages={self.last_given_at!r}" \
               f" dirty={self.dirty!r}>"

    @classmethod
    def from_record(cls, record):
        """Create a cache entry from a database record. This copies all shared fields and sets `dirty` to False."""
        return cls(record.total_xp, record.last_given_at, record.total_messages, False)


class GuildXPSettings(db.DatabaseTable):
    """Database table containing per-guild settings related to XP gain."""
    __tablename__ = "levels_guild_settings"
    __uniques__ = "guild_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            xp_min int NOT NULL,
            xp_max int NOT NULL,
            xp_cooldown int NOT NULL,
            entropy_value int NOT NULL,
            lvl_up_msgs bigint NOT NULL,
            enabled boolean NOT NULL
            )""")

    def __init__(self, guild_id, xp_min, xp_max, xp_cooldown, entropy_value, enabled, lvl_up_msgs):
        super().__init__()
        self.guild_id = guild_id
        self.xp_min = xp_min
        self.xp_max = xp_max
        self.xp_cooldown = xp_cooldown
        self.entropy_value = entropy_value
        self.enabled = enabled
        self.lvl_up_msgs = lvl_up_msgs

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildXPSettings(guild_id=result.get("guild_id"), xp_min=result.get("xp_min"), xp_max=result.get("xp_max"),
                                  xp_cooldown=result.get("xp_cooldown"), entropy_value=result.get("entropy_value"), enabled=result.get("enabled"),
                                  lvl_up_msgs=result.get("lvl_up_msgs"))
            result_list.append(obj)
        return result_list


def setup(bot):
    """Add the levels cog to a bot."""
    bot.add_cog(Levels(bot))
