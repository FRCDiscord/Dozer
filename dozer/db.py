"""Provides database storage for the Dozer Discord bot"""

import asyncpg
import discord


async def db_init(db_url):
    """Initializes the database connection"""
    global Pool
    Pool = await asyncpg.create_pool(dsn=db_url, command_timeout=15)


async def db_migrate():
    """Gets all subclasses and checks their migrations."""
    async with Pool.acquire() as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS versions (
        table_name text PRIMARY KEY,
        version_num int NOT NULL
        )""")
    for cls in DatabaseTable.__subclasses__():
        exists = await Pool.fetchrow(f"""SELECT EXISTS(
        SELECT 1
        FROM information_schema.tables
        WHERE
        table_name = $1)""", cls.__tablename__)
        if exists['exists']:
            version = await Pool.fetchrow("""SELECT version_num FROM versions WHERE table_name = $1""", cls.__tablename__)
            if version is None:
                # Migration/creation required, go to the function in the subclass for it
                await cls.initial_migrate()
            elif int(version["version_num"]) < len(cls.__versions__):
                # the version in the DB is less than the version in the bot, run all the migrate scripts necessary
                for i in range(int(version["version_num"]) + 1, len(cls.__versions__)-2):
                    # Run the update script for this version!
                    cls.__versions__[i]()
        else:
            await cls.initial_create()


class DatabaseTable:
    __tablename__ = None

    # Declare the migrate/create functions
    @classmethod
    async def initial_create(cls):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY
            )""")

    @classmethod
    async def initial_migrate(cls):
        """Migrate the table from the SQLalchemy based system to the asyncpg system. Define this yourself, or leave it
        blank if no migration is necessary."""


class ConfigCache:
    """Class that will reduce calls to sqlalchemy as much as possible. Has no growth limit (yet)"""
    def __init__(self, table):
        self.cache = {}
        self.table = table

    @staticmethod
    def _hash_dict(dic):
        """Makes a dict hashable by turning it into a tuple of tuples"""
        # sort the keys to make this repeatable; this allows consistency even when insertion order is different
        return tuple((k, dic[k]) for k in sorted(dic))

    def query_one(self, **kwargs):
        """Query the cache for an entry matching the kwargs, then try again using the database."""
        query_hash = self._hash_dict(kwargs)
        if query_hash not in self.cache:
            with Session() as session:
                self.cache[query_hash] = session.query(self.table).filter_by(**kwargs).one_or_none()
        return self.cache[query_hash]

    def query_all(self, **kwargs):
        """Query the cache for all entries matching the kwargs, then try again using the database."""
        query_hash = self._hash_dict(kwargs)
        if query_hash not in self.cache:
            with Session() as session:
                self.cache[query_hash] = session.query(self.table).filter_by(**kwargs).all()
        return self.cache[query_hash]

    def invalidate_entry(self, **kwargs):
        """Removes an entry from the cache if it exists - used to mark changed data."""
        query_hash = self._hash_dict(kwargs)
        if query_hash in self.cache:
            del self.cache[query_hash]
    @classmethod
    async def set_initial_version(cls):
        await Pool.execute("""INSERT INTO versions (table_name, version_num) 
                                          VALUES (?,?)""", cls.__tablename__, 0)

    __versions__ = {}

    __uniques__ = []

    def __init__(self):
        """Blank constructor, fill with your database roles exactly like the variable names. Also make sure your
         __uniques__ property is overridden."""

    async def update_or_add(self):
        """Assign the attribute to this object, then call this method to either insert the object if it doesn't exist in
        the DB or update it if it does exist. It will update every column not specified in __uniques__."""
        keys = []
        values = []
        for var, value in self.__dict__.items():
            # Done so that the two are guaranteed to be in the same order, which isn't true of keys() and values()
            keys.append(var)
            values.append(value)
        updates = ""
        for key in keys:
            if key in self.__uniques__:
                # Skip updating anything that has a unique constraint on it
                continue
            updates += f"{key} = EXCLUDED.{key}"
            if keys.index(key) == len(keys)-1:
                updates += " ;"
            else:
                updates += ", \n"
        async with Pool.acquire() as conn:
            conn.execute(f"""
            INSERT INTO {self.__tablename__} ({", ".join(keys)})
            VALUES($1)
            ON CONFLICT ({", ".join(self.__uniques__)}) DO UPDATE
            SET {updates}
            """, values)

    def __repr__(self):
        values = ""
        first = True
        for key, value in self.__dict__.items():
            if not first:
                values += ", "
                first = False
            values += f"{key}: {value}"
        return f"{self.__tablename__}: < {', '.join(self.__dict__.items())}>"

    # Class Methods

    @classmethod
    async def get_by_attribute(cls, obj_id, column_name):
        """Gets a list of all objects with a given attribute. This will grab all attributes, it's more efficient to
        write your own SQL queries than use this one, but for a simple query this is fine."""
        async with Pool.acquire() as conn:  # Use transaction here?
            stmt = await conn.prepare(f"""SELECT * FROM {cls.__tablename__} WHERE {column_name} = ?""")
            results = stmt.fetch(obj_id)
            list = []
            for result in results:
                obj = cls()
                for var in cls().__dict__:
                    setattr(obj, var, result.get(var))
                list.append(obj)
            return list

    @classmethod
    async def get_by_id(cls, obj_id):
        """Get an instance of this object by it's primary key, id. This function will work for most subclasses using
        `id` as it's primary key."""
        await cls.get_by_attribute(obj_id, "id")

    @classmethod
    async def get_by_guild(cls, guild_id, guild_column_name = "guild_id"):
        await cls.get_by_attribute(guild_id, guild_column_name)

    @classmethod
    async def get_by_channel(cls, channel_id, channel_column_name = "channel_id"):
        await cls.get_by_attribute(channel_id, channel_column_name)

    @classmethod
    async def get_by_user(cls, user_id, user_column_name="user_id"):
        await cls.get_by_attribute(user_id, user_column_name)

    @classmethod
    async def get_by_role(cls, role_id, role_column_name="role_id"):
        await cls.get_by_attribute(role_id, role_column_name)

