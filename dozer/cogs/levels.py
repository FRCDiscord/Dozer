"""Records members' XP and level."""

import logging
from datetime import timedelta, timezone

from discord.ext.tasks import loop

from ._utils import *
from .. import db

logger = logging.getLogger(__name__)


class Levels(Cog):
    """Commands and event handlers for managing levels and XP."""

    xp_per_message = 15
    xp_cooldown = timedelta(minutes=1)

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
                cached_member = MemberXPCache(0, None, False)
            self._xp_cache[(message.guild.id, message.author.id)] = cached_member

        timestamp = message.created_at.replace(tzinfo=timezone.utc)
        if cached_member.last_given_at is None or timestamp - cached_member.last_given_at > self.xp_cooldown:
            cached_member.total_xp += self.xp_per_message
            cached_member.last_given_at = timestamp
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
            to_write.append((guild_id, user_id, cached_member.total_xp, cached_member.last_given_at))
            cached_member.dirty = False

        if not to_write:
            logger.debug("Sync task skipped, nothing to do")
            return
        # Query written manually to insert all records at once
        async with db.Pool.acquire() as conn:
            await conn.executemany(f"INSERT INTO {MemberXP.__tablename__} (guild_id, user_id, total_xp, last_given_at)"
                                   f" VALUES ($1, $2, $3, $4) ON CONFLICT ({MemberXP.__uniques__}) DO UPDATE"
                                   f" SET total_xp = EXCLUDED.total_xp, last_given_at = EXCLUDED.last_given_at",
                                   to_write)
        logger.debug("Inserted/updated %d record(s)", len(to_write))

    sync_task = loop(minutes=1)(sync_to_database)

    @sync_task.before_loop
    async def before_sync(self):
        """Do preparation work before starting the periodic timer to sync XP with the database."""
        await self.bot.wait_until_ready()

    def cog_unload(self):
        """Detach from the running bot and cancel long-running code as the cog is unloaded."""
        self.sync_task.stop()


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
            last_given_at timestamptz NOT NULL,
            PRIMARY KEY (guild_id, user_id)
            )""")

    def __init__(self, guild_id, user_id, total_xp, last_given_at):
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.total_xp = total_xp
        self.last_given_at = last_given_at

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = MemberXP(guild_id=result.get("guild_id"), user_id=result.get("user_id"),
                           total_xp=result.get("total_xp"), last_given_at=result.get("last_given_at"))
            result_list.append(obj)
        return result_list


class MemberXPCache:
    """ A cached record of a user's XP.
        This has all of the fields of `MemberXP` except the primary key, and an additional `dirty` flag that indicates
        whether the record has been changed since it was loaded from the database or created.
    """

    def __init__(self, total_xp, last_given_at, dirty):
        self.total_xp = total_xp
        self.last_given_at = last_given_at
        self.dirty = dirty

    def __repr__(self):
        return f"<MemberXPCache total_xp={self.total_xp!r} last_given_at={self.last_given_at!r} dirty={self.dirty!r}>"

    @classmethod
    def from_record(cls, record):
        """Create a cache entry from a database record. This copies all shared fields and sets `dirty` to False."""
        return cls(record.total_xp, record.last_given_at, False)


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
