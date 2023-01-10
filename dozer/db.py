"""Provides database storage for the Dozer Discord bot"""
from typing import List, Dict

import asyncpg
from loguru import logger

Pool = None


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
    logger.info("Checking for db migrations")
    for cls in DatabaseTable.__subclasses__():
        exists = await Pool.fetchrow("""SELECT EXISTS(
        SELECT 1
        FROM information_schema.tables
        WHERE
        table_name = $1)""", cls.__tablename__)
        if not exists['exists']:
            await cls.initial_create()

        version = await Pool.fetchrow("""SELECT version_num FROM versions WHERE table_name = $1""",
                                        cls.__tablename__)
        if version is None:
            # Migration/creation required, go to the function in the subclass for it
            await cls.initial_migrate()
            version = {"version_num": 0}
        if int(version["version_num"]) < len(cls.__versions__):
            # the version in the DB is less than the version in the bot, run all the migrate scripts necessary
            logger.info(f"Table {cls.__tablename__} is out of date attempting to migrate")
            for i in range(int(version["version_num"]), len(cls.__versions__)):
                # Run the update script for this version!
                await cls.__versions__[i](cls)
                logger.info(f"Successfully updated table {cls.__tablename__} from version {i} to {i + 1}")
            async with Pool.acquire() as conn:
                await conn.execute("""UPDATE versions SET version_num = $1 WHERE table_name = $2""",
                                    len(cls.__versions__), cls.__tablename__)
    logger.info("All db migrations complete.")


class DatabaseTable:
    """Defines a database table"""
    __tablename__: str = ''
    __versions__: List[int] = []
    __uniques__: List[str] = []

    # Declare the migrate/create functions
    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        raise NotImplementedError("Database schema not implemented!")

    @classmethod
    async def initial_migrate(cls):
        """Create a version entry in the versions table"""
        async with Pool.acquire() as conn:
            await conn.execute("""INSERT INTO versions VALUES ($1, 0)""", cls.__tablename__)

    @staticmethod
    def nullify():
        """Function to be referenced when a table entry value needs to be set to null"""

    async def update_or_add(self):
        """Assign the attribute to this object, then call this method to either insert the object if it doesn't exist in
        the DB or update it if it does exist. It will update every column not specified in __uniques__."""
        keys = []
        values = []
        for var, value in self.__dict__.items():
            # Done so that the two are guaranteed to be in the same order, which isn't true of keys() and values()
            if value is self.nullify:
                keys.append(var)
                values.append(None)
            elif value is not None:
                keys.append(var)
                values.append(value)

        updates = ""
        for key in keys:
            if key in self.__uniques__:
                # Skip updating anything that has a unique constraint on it
                continue
            updates += f"{key} = EXCLUDED.{key}"
            if keys.index(key) == len(keys) - 1:
                updates += " ;"
            else:
                updates += ", \n"
        async with Pool.acquire() as conn:
            if updates:
                statement = f"""
                INSERT INTO {self.__tablename__} ({", ".join(keys)})
                VALUES({','.join(f'${i + 1}' for i in range(len(values)))})
                ON CONFLICT ({self.__uniques__}) DO UPDATE
                SET {updates}
                """
            else:
                statement = f"""
                INSERT INTO {self.__tablename__} ({", ".join(keys)})
                VALUES({','.join(f'${i + 1}' for i in range(len(values)))})
                ON CONFLICT ({self.__uniques__}) DO NOTHING;
                """
            await conn.execute(statement, *values)

    def __repr__(self):
        values = ""
        first = True
        for key, value in self.__dict__.items():
            if not first:
                values += ", "
                first = False
            values += f"{key}: {value}"
        return f"{self.__tablename__}: <{values}>"

    # Class Methods

    @classmethod
    async def get_by(cls, **filters):
        """Get a list of all records matching the given column=value criteria. This will grab all attributes, it's more
        efficent to write your own SQL queries than use this one, but for a simple query this is fine."""
        async with Pool.acquire() as conn:
            statement = f"SELECT * FROM {cls.__tablename__}"
            if filters:
                # note: this code relies on subsequent iterations of the same dict having the same iteration order.
                # This is an implementation detail of CPython 3.6 and a language guarantee in Python 3.7+.
                conditions = " AND ".join(f"{column_name} = ${i + 1}" for (i, column_name) in enumerate(filters))
                statement = f"{statement} WHERE {conditions};"
            else:
                statement += ";"
            return await conn.fetch(statement, *filters.values())

    @classmethod
    async def delete(cls, **filters):
        """Deletes by any number of criteria specified as column=value keyword arguments. Returns the number of entries deleted"""
        async with Pool.acquire() as conn:
            if filters:
                # This code relies on properties of dicts - see get_by
                conditions = " AND ".join(f"{column_name} = ${i + 1}" for (i, column_name) in enumerate(filters))
                statement = f"DELETE FROM {cls.__tablename__} WHERE {conditions};"
            else:
                # Should this be a warning/error? It's almost certainly not intentional
                statement = f"TRUNCATE {cls.__tablename__};"
            return await conn.execute(statement, *filters.values())

    @classmethod
    async def set_initial_version(cls):
        """Sets initial version"""
        await Pool.execute("""INSERT INTO versions (table_name, version_num) VALUES ($1,$2)""", cls.__tablename__, 0)


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

    async def query_one(self, **kwargs):
        """Query the cache for an entry matching the kwargs, then try again using the database."""
        query_hash = self._hash_dict(kwargs)
        if query_hash not in self.cache:
            self.cache[query_hash] = await self.table.get_by(**kwargs)
            if len(self.cache[query_hash]) == 0:
                self.cache[query_hash] = None
            else:
                self.cache[query_hash] = self.cache[query_hash][0]
        return self.cache[query_hash]

    async def query_all(self, **kwargs):
        """Query the cache for all entries matching the kwargs, then try again using the database."""
        query_hash = self._hash_dict(kwargs)
        if query_hash not in self.cache:
            self.cache[query_hash] = await self.table.get_by(**kwargs)
        return self.cache[query_hash]

    def invalidate_entry(self, **kwargs):
        """Removes an entry from the cache if it exists - used to mark changed data."""
        query_hash = self._hash_dict(kwargs)
        if query_hash in self.cache:
            del self.cache[query_hash]

    __versions__: Dict[str, int] = {}

    __uniques__: List[str] = []
