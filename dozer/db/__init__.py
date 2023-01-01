"""Provides database storage for the Dozer Discord bot"""

# pylint generates false positives on this warning
# pylint: disable=unsupported-membership-test
from typing import List, Dict, Tuple
import asyncpg
from loguru import logger
from .pqt import Column, Col

__all__ = ["Pool", "Column", "Col", "db_init", "db_migrate", "DatabaseTable", "ORMTable", "ConfigCache"]

Pool: asyncpg.Pool = None


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
    for cls in DatabaseTable.__subclasses__() + ORMTable.__subclasses__():

        if cls is ORMTable:  # abstract class, do not check
            continue
        
        if not cls.__tablename__:
            raise ValueError(f"{cls.__name__}.__tablename__ cannot be blank!")
        if isinstance(cls, ORMTable) and cls.__uniques__ and not isinstance(cls.__uniques__, tuple):
            raise ValueError(f"{cls.__name__}.__uniques__ must be a tuple!")


        exists = await Pool.fetchrow("""SELECT EXISTS(
        SELECT 1
        FROM information_schema.tables
        WHERE
        table_name = $1)""", cls.__tablename__)
        if not exists['exists']:
            await cls.initial_create()
            version = None
        else:
            version = await Pool.fetchrow("""SELECT version_num FROM versions WHERE table_name = $1""",
                                            cls.__tablename__)
        if version is None:
            # Migration/creation required, go to the function in the subclass for it
            await cls.initial_migrate()
            version = {"version_num": 0}

        if cls.__versions__ is None:
            # this uses the ORMTable autoversioner
            await cls.migrate_to_version(int(version["version_num"]))

        elif int(version["version_num"]) < len(cls.__versions__):
            # the version in the DB is less than the version in the bot, run all the migrate scripts necessary
            logger.info(f"Table {cls.__tablename__} is out of date attempting to migrate")
            for i in range(int(version["version_num"]), len(cls.__versions__)):
                # Run the update script for this version!
                await cls.__versions__[i](cls)
                logger.info(f"Successfully updated table {cls.__tablename__} from version {i} to {i + 1}")
            async with Pool.acquire() as conn:
                await conn.execute("""UPDATE versions SET version_num = $1 WHERE table_name = $2""",
                                    len(cls.__versions__), cls.__tablename__)


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


class ORMTable(DatabaseTable):
    """ORM tables are a new variant on DatabaseTables:

    * they are defined from class attributes
    * initial_create, initial_migrate, get_by, delete, and update_or_add (upsert) are handled for you
    * ability to instantiate objects directly from the results of SQL queries using from_record
    * inferred versioning from column parameters

    This class can vastly reduce the amount of boilerplate in a codebase.

    notes: 
     * __uniques__ MUST be a tuple of primary key column names! 
       Do not set it to a string! Runtime will check for this and yell at you!
     * By default, __version__ is None. This means that versions/migrations will be computed from arguments given to Column.
       You can set __version__ to a List for the default functionality of calling migration functions if desired.


    For example:

    ```python
    class StarboardConfig(db.orm.ORMTable):
        __tablename__ = 'starboard_settings'
        __uniques__ = ('guild_id',) 
        
        # the column definitions
        guild_id: int     = db.Column("bigint NOT NULL")
        channel_id: int   = db.Column("bigint NOT NULL")
        star_emoji: str   = db.Column("varchar NOT NULL")
        cancel_emoji: str = db.Column("varchar")
        threshold: int    = db.Column("bigint NOT NULL")

        # this parameter could be added later down the line, and it will be added using ALTER TABLE.
        some_new_col: int = db.Column("bigint NOT NULL DEFAULT 10", version=1)
    ```
    
    will produce a functionally equivalent class without overriding initial_create or get_by.

    """
    __tablename__: str = ''
    __versions__: Tuple[int] | None = None
    __uniques__: Tuple[str] = tuple()

    _columns: Dict[str, Column] = None


    # Declare the migrate/create functions
    @classmethod
    async def initial_create(cls):
        """Create the table in the database. Already implemented for you. Can still override if desired."""

        logger.debug(cls.__name__ + " process")

        columns = cls.get_columns()
        # assemble "column = Column('integer not null') into column integer not null, "
        query_params = ", ".join(map(" ".join, zip(columns.keys(), (c.sql for c in columns.values()))))

        if cls.__uniques__:
            # TODO: determine if we should still use __uniques__ or have primary key data in Column
            query_params += f", PRIMARY KEY({', '.join(k for k in cls.__uniques__)})"

        query_str = f"CREATE TABLE {cls.__tablename__}({query_params})"

        logger.debug("exec " + query_str)
        async with Pool.acquire() as conn:
            await conn.execute(query_str)


    @staticmethod
    def nullify():
        """Function to be referenced when a table entry value needs to be set to null"""

    def __init__(self, *args, **kwargs):
        """
        yeah the one drawback of this approach is that you don't get hints for constructors anymore
        which doesn't stop language servers from somehow figuring out how to do this with dataclasses
        turns out dataclasses use dark magic 
        (they dynamically generate and eval an __init__ which they staple onto the class)

        you can just avoid this by overriding the init functions anyway, but if you do, 
        it's suggested that you include all the columns as arguments as from_record will call
        the constructor with them using the ** operator

        if that is a problem, just override from_record to not do that 

        """
        self.__dict__.update({k: v for k, v in kwargs.items() if k in self.get_columns()})
        super().__init__()

    async def update_or_add(self):
        """Assign the attribute to this object, then call this method to either insert the object if it doesn't exist in
        the DB or update it if it does exist. It will update every column not specified in __uniques__."""
        keys = []
        values = []
        for var, value in self.__dict__.items():
            if var not in self.get_columns():
                continue
            # Done so that the two are guaranteed to be in the same order, which isn't true of keys() and values()
            keys.append(var)
            values.append(None if value is self.nullify else value)

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
        
        primary_key = ", ".join(self.__uniques__)

        async with Pool.acquire() as conn:
            if updates:
                statement = f"""
                INSERT INTO {self.__tablename__} ({", ".join(keys)})
                VALUES({','.join(f'${i + 1}' for i in range(len(values)))})
                ON CONFLICT ({primary_key}) DO UPDATE
                SET {updates}
                """
            else:
                statement = f"""
                INSERT INTO {self.__tablename__} ({", ".join(keys)})
                VALUES({','.join(f'${i + 1}' for i in range(len(values)))})
                ON CONFLICT ({primary_key}) DO NOTHING;
                """

            logger.debug("exec " + statement)
            await conn.execute(statement, *values)

    def __repr__(self):
        # repr is supposed to be a representation of the object
        # usually you want eval(repr(obj)) == obj more or less
        return self.__class__.__name__ + "(" + ", ".join(f"{key}={val!r}" for key, val in \
                {key: getattr(self, key) for key in self._columns.keys()}.items()) + ")"

    # Class Methods

    @classmethod
    def get_columns(cls) -> Dict[str, Column]:
        """Returns all columns in the table. Also initializes the column cache."""
        if cls._columns is not None:
            return cls._columns
        
        cls._columns = {name: val for name, val in vars(cls).items() if isinstance(val, Column)}
        return cls._columns


    @classmethod
    def from_record(cls, record: asyncpg.Record):
        """Converts an asyncpg query record into an instance of the class. Nonexistent entries will get filled with None."""
        if record is None:
            return None

        return cls(**{k: record.get(k) for k in cls.get_columns().keys()})

    @classmethod
    async def get_by(cls, **filters) -> list:
        """Selects a list of all records matching the given column=value criteria. 
        Since pretty much every subclass overrides this to return lists of instantiated objects rather than queries,
        we simply automate this.
        """
        async with Pool.acquire() as conn:
            statement = f"SELECT * FROM {cls.__tablename__}"
            if filters:
                # note: this code relies on subsequent iterations of the same dict having the same iteration order.
                # This is an implementation detail of CPython 3.6 and a language guarantee in Python 3.7+.
                conditions = " AND ".join(f"{column_name} = ${i + 1}" for (i, column_name) in enumerate(filters))
                statement = f"{statement} WHERE {conditions};"
            else:
                statement += ";"
            logger.debug("exec " + statement)
            records = await conn.fetch(statement, *filters.values())
        return [*map(cls.from_record, records)]
    
    @classmethod
    async def get_one(cls, **filters):
        """It's like get_by except it returns exactly one record or None."""
        return ((await cls.get_by(**filters)) or [None])[0]
    

    @classmethod
    async def migrate_to_version(cls, prev_version:int, next_version:int=None):
        """Migrates current table from prev_version up to next_version (setting next_version=None assumes latest)
        This only supports ALTER TABLE ADD COLUMN type edits at the moment, but if you
        really need more complex functionality, feel free to override this function.

        If __versions__ is set to None, this will get called in db_migrate.
        """
        versions = {}
        for col_name, col in cls.get_columns().items():
            v = col.version
            if v <= prev_version or (next_version is not None and v > next_version):
                continue 
            if v not in versions:
                versions[v] = [(col_name, col)]
            else:
                versions[v].append((col_name, col))
        
        async with Pool.acquire() as conn:
            for vnum in sorted(versions.keys()):
                for col_name, col in versions[vnum]:
                    await conn.execute(f"ALTER TABLE {cls.__tablename__} ADD COLUMN {col_name} {col.sql};")
                logger.info(f"updated {cls.__tablename__} from version {prev_version} to {vnum}")
                prev_version = vnum



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
