"""Records members' XP and level."""

import functools
import asyncio
import logging
import math
from datetime import timedelta, timezone
import requests
import time
import discord
from discord.ext.commands import guild_only, has_permissions
from discord.ext.tasks import loop

from ._utils import *
from .. import db

logger = logging.getLogger(__name__)


class Levels(Cog):
    """Commands and event handlers for managing levels and XP."""

    xp_per_message = 15
    xp_cooldown = timedelta(minutes=1)
    cache_size = 750

    def __init__(self, bot):
        super().__init__(bot)
        self._loop = bot.loop
        self._guild_settings = {}
        self._xp_cache = {}  # dct[(guild_id, user_id)] = MemberXPCache(...)
        self._loop.create_task(self.preload_cache())
        self.sync_task.start()

    async def preload_cache(self):
        """Load all guild settings from the database."""
        await self.bot.wait_until_ready()
        logger.info("Preloading guild settings")
        records = await GuildXPSettings.get_by()  # no filters, get all
        for record in records:
            self._guild_settings[record.guild_id] = record
        logger.info("Loaded settings for %d guilds", len(self._guild_settings))
        # Load subset of member XP records here?

    # TODO: For god's sake don't put this in production
    @command(aliases=["mee6sync"])
    @discord.ext.commands.max_concurrency(1, wait=False)  # Only allows one instance of this command to run at a time globally
    @discord.ext.commands.cooldown(rate=1, per=3600, type=discord.ext.commands.BucketType.guild)  # A cooldown of one hour per guild to prevent spam
    @has_permissions(administrator=True)
    async def meesyncs(self, ctx):
        guild_id = ctx.guild.id
        guild_id = 176186766946992128
        progress_template = "Currently syncing from Mee6 API please wait... Page: {page}"
        msg = await ctx.send(progress_template.format(page="N/A"))
        for page in range(0, 100000):
            request = requests.get("https://mee6.xyz/api/plugins/levels/leaderboard/{guildID}?page={page}".format(guildID=guild_id, page=page))
            data = request.json()
            if len(data["players"]) > 0:
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
            time.sleep(1.25)

        ent = GuildXPSettings(
            guild_id=int(guild_id),
            enabled=True
        )
        await ent.update_or_add()
        await ctx.send("Done")

    meesyncs.example_usage = """
        `{prefix}meesyncs`: Sync ranking data from the mee6 API to dozer's database
        """

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

    @Cog.listener('on_message')
    async def give_message_xp(self, message):
        """Handle giving XP to a user for a message."""
        if message.author.bot or not message.guild:
            return
        guild_settings = self._guild_settings.get(message.guild.id)
        if guild_settings is None or not guild_settings.enabled:
            return

        cached_member = self._xp_cache.get((message.guild.id, message.author.id))
        if cached_member is None:
            logger.debug("Cache miss: guild_id=%d, user_id=%d", message.guild.id, message.author.id)
            records = await MemberXP.get_by(guild_id=message.guild.id, user_id=message.author.id)
            if records:
                logger.debug("Loading from database")
                cached_member = MemberXPCache.from_record(records[0])
            else:
                logger.debug("Creating from scratch")
                cached_member = MemberXPCache(0, None, False, 0)
            self._xp_cache[(message.guild.id, message.author.id)] = cached_member

        timestamp = message.created_at.replace(tzinfo=timezone.utc)
        if cached_member.last_given_at is None or timestamp - cached_member.last_given_at > self.xp_cooldown:
            cached_member.total_xp += self.xp_per_message
            cached_member.last_given_at = timestamp
            cached_member.total_messages += 1
            cached_member.dirty = True

    async def sync_to_database(self):
        """Sync dirty records to the database, and evict others from the cache."""
        logger.info("Syncing XP to database")

        # Deleting from a dict while iterating will error, so collect the keys up front and iterate that
        # Note that all mutation of `self._xp_cache` happens before the first yield point to prevent race conditions
        keys = list(self._xp_cache.keys())
        to_write = []  # records to write to the database
        for (guild_id, user_id) in keys:
            cached_member = self._xp_cache[(guild_id, user_id)]
            if not cached_member.dirty:
                # Evict records that haven't changed since last run from cache to conserve memory
                del self._xp_cache[(guild_id, user_id)]
                continue
            to_write.append((guild_id, user_id, cached_member.total_xp, cached_member.total_messages, cached_member.last_given_at))
            cached_member.dirty = False

        if not to_write:
            logger.debug("Sync task skipped, nothing to do")
            return
        # Query written manually to insert all records at once
        async with db.Pool.acquire() as conn:
            await conn.executemany(f"INSERT INTO {MemberXP.__tablename__} (guild_id, user_id, total_xp, total_messages, last_given_at)"
                                   f" VALUES ($1, $2, $3, $4, $5) ON CONFLICT ({MemberXP.__uniques__}) DO UPDATE"
                                   f" SET total_xp = EXCLUDED.total_xp, total_messages = EXCLUDED.total_messages, last_given_at = "
                                   f"EXCLUDED.last_given_at",
                                   to_write)
        logger.debug("Inserted/updated %d record(s)", len(to_write))

    @loop(minutes=10)
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
            logger.warning("Task syncing records was cancelled prematurely, restarting")
        else:
            # exc could be None if the task returns normally, but that would also be an error
            logger.error("Task syncing records failed: %r", exc)
        finally:
            self.sync_task.start()

    @command()
    @guild_only()
    async def rank(self, ctx, *, member: discord.Member = None):
        """Get a user's ranking on the XP leaderboard.
        If no member is passed, the caller's ranking is shown.
        """
        member = member or ctx.author

        await self.sync_to_database()
        self._ensure_sync_running()

        # Make Postgres compute the rank for us (need WITH-query so rank() sees records for every user)
        record = await db.Pool.fetchrow(f"""
            WITH ranked_xp AS (
                SELECT user_id, total_xp, rank() OVER (ORDER BY total_xp DESC) FROM {MemberXP.__tablename__}
                WHERE guild_id = $1
            ) SELECT total_xp, rank FROM ranked_xp WHERE user_id = $2;
        """, ctx.guild.id, member.id)

        if record:
            total_xp, rank = record
        else:
            await ctx.send("That user isn't on the leaderboard.")
            return

        count = await db.Pool.fetchval(f"""SELECT count(*) FROM {MemberXP.__tablename__} WHERE guild_id = $1;""",
                                       ctx.guild.id)
        level = self.level_for_total_xp(total_xp)
        level_floor = self.total_xp_for_level(level)
        level_xp = self.total_xp_for_level(level + 1) - level_floor

        embed = discord.Embed(color=member.color)
        embed.description = (f"Level {level}, {total_xp - level_floor}/{level_xp} XP to level up ({total_xp} total)\n"
                             f"#{rank} of {count} in this server")
        embed.set_author(name=member.display_name, icon_url=member.avatar_url_as(format='png', size=64))
        await ctx.send(embed=embed)

    rank.example_usage = """
    `{prefix}rank`: show your ranking
    `{prefix}rank coolgal#1234`: show another user's ranking
    """

    @staticmethod
    def _fmt_member(guild, user_id):
        member = guild.get_member(user_id)
        if member:
            return str(member)
        else:
            return "Missing member"

    @command()
    @guild_only()
    async def levels(self, ctx):
        """Show the XP leaderboard for this server."""

        await self.sync_to_database()
        self._ensure_sync_running()

        # Order by total_xp needs a tiebreaker, otherwise all records with equal XP have the same rank
        # This causes rankings like #1, #1, #1, #4, #4, #6, ...
        # user_id is arbitrary, chosen because it is guaranteed to be unique between two records in the same guild
        records = await db.Pool.fetch(f"""
            SELECT user_id, total_xp, rank() OVER (ORDER BY total_xp DESC, user_id) FROM {MemberXP.__tablename__}
            WHERE guild_id = $1 ORDER BY rank;
        """, ctx.guild.id)

        # TODO load only a few pages of data at a time with a cursor
        embeds = []
        for page_num, page in enumerate(chunk(records, 10)):
            embed = discord.Embed(title=f"Rankings for {ctx.guild}", color=discord.Color.blue())
            embed.description = '\n'.join(f"#{rank}: {self._fmt_member(ctx.guild, user_id)}"
                                          f" (lvl {self.level_for_total_xp(total_xp)}, {total_xp} XP)"
                                          for (user_id, total_xp, rank) in page)
            embed.set_footer(text=f"Page {page_num + 1} of {math.ceil(len(records) / 10)}")
            embeds.append(embed)
        await paginate(ctx, embeds)

    levels.example_usage = """
    `{prefix}levels`: show the XP leaderboard
    """


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
            total_xp int NOT NULL,
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

    def __init__(self, total_xp, last_given_at, dirty, total_messages):
        self.total_xp = total_xp
        self.total_messages = total_messages
        self.last_given_at = last_given_at
        self.dirty = dirty

    def __repr__(self):
        return f"<MemberXPCache total_xp={self.total_xp!r} last_given_at={self.last_given_at!r} dirty={self.dirty!r}>"

    @classmethod
    def from_record(cls, record):
        """Create a cache entry from a database record. This copies all shared fields and sets `dirty` to False."""
        return cls(record.total_xp, record.last_given_at, False, record.total_messages)


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
            enabled boolean NOT NULL
            )""")

    def __init__(self, guild_id, enabled):
        super().__init__()
        self.guild_id = guild_id
        self.enabled = enabled

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildXPSettings(guild_id=result.get("guild_id"), enabled=result.get("enabled"))
            result_list.append(obj)
        return result_list


def setup(bot):
    """Add the levels cog to a bot."""
    bot.add_cog(Levels(bot))
