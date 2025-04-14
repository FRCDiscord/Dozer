"""Provides database storage for the Dozer Discord bot"""

# pylint generates false positives on this warning
# pylint: disable=unsupported-membership-test
from typing import List, Dict, Tuple, Callable, TypeVar
import asyncpg
from loguru import logger

__all__ = ["Pool", "Column", "Col", "db_init", "db_migrate", "DatabaseTable", "ORMTable", "ConfigCache"]

Pool: asyncpg.Pool = None

class Column:
    """Represents a sql column.
    Includes an optional version parameter for columns added later, and an alter_tbl field.


    SQL injectability: don't supply user-provided input to the sql or alter_tbl fields.
    """
    def __init__(self, sql: str, version=0, alter_tbl=None):
        """
        sql: the type and parameters, such as "bigint NOT NULL". In general, this translates to
        
            CREATE TABLE tbl ({col_name} {self.sql}, ...) ...;

            during initial_create.
            

        version: the first table version this column appears in. Defaults zero.
            Optional if __version__ is a List.

        alter_tbl: 
            if None, run 
                ALTER TABLE ADD COLUMN {col_name} {self.sql}; 
            to add the table.

            If not None, run
                ALTER TABLE {alter_tbl};
            instead.

        """
        self.sql: str = sql
        self.version: int = version
        self.alter_tbl = alter_tbl

Col = Column

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
            await cls.initial_migrate()
        version = await Pool.fetchrow("""SELECT version_num FROM versions WHERE table_name = $1""",
                                        cls.__tablename__)
        if version is None:
            # Migration/creation required, go to the function in the subclass for it
            await cls.initial_migrate()
            version = {"version_num": 0}

        current_version = int(version['version_num'])
        if cls.__versions__ is None:
            # this uses the ORMTable autoversioner
            max_cls_version = max(cls.get_columns().values(), key=lambda c: c.version)
            if current_version > max_cls_version:
                raise RuntimeError(f"database version for {cls.__name__} ({cls.__tablename__}) is higher than in code "
                                   f"({current_version} > {max_cls_version})")

            await cls.migrate_to_version(current_version, None)

        elif current_version < len(cls.__versions__):
            # the version in the DB is less than the version in the bot, run all the migrate scripts necessary
            logger.info(f"Table {cls.__tablename__} is out of date attempting to migrate")
            for i in range(current_version, len(cls.__versions__)):
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
    __versions__: List[Callable] = []
    __uniques__: str = ''

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

# typing.Self is in 3.11 which is a shade too new for us
TORMTable = TypeVar("TORMTable", bound="ORMTable")

class ORMTable(DatabaseTable):
    """ORM tables are a new variant on DatabaseTables:

    * they are defined from class attributes
    * initial_create, initial_migrate, get_by, delete, and update_or_add (upsert) are handled for you
    * ability to instantiate objects directly from the results of SQL queries using from_record
    * inferred versioning from column parameters (mostly adds columns)

    This class can vastly reduce the amount of boilerplate in a codebase.

    Differences from DatabaseTable:
     * __uniques__ MUST be a tuple of primary key column names! 
       Do not set it to a string! Runtime will check for this and yell at you!
     * By default, __version__ is None. This means that versions/migrations will be computed from arguments given to Column.
     * initial_create/initial_migrate will create the latest version of the table, rather than version 0.
    

    Versioning:
     * In general, columns should be defined using the latest version of the schema.
      * If your table previously had an id field that's now channel_id, name the thing

        channel_id: int = db.Column("bigint NOT NULL")

      * The default versioning scheme looks at db.Column.version to see when the first version a column is introduced.
        It will then either just add the column using ALTER TABLE ADD COLUMN or run a custom script via whatever script is in Column.alter_tbl.
        
      * You can set __version__ to a List for the default functionality of calling migration functions in order.

        You can also override cls.initial_create and cls.initial_migrate to have tables created at version 0 and upgraded all the way up, 
        like DatabaseTable.


    Worked example:

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
    __versions__: List[Callable] | None = None
    __uniques__: Tuple[str] = tuple()

    _columns: Dict[str, Column] = None


    # Declare the migrate/create functions
    @classmethod
    async def initial_create(cls):
        """Create the table in the database. Already implemented for you. Can still override if desired.
        Note that unlike DatabaseTable this will create a table directly from the latest version of the class,
        rather than always version 0.
        """

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
    def from_record(cls, record: asyncpg.Record) -> TORMTable:
        """Converts an asyncpg query record into an instance of the class. Nonexistent entries will get filled with None."""
        if record is None:
            return None

        return cls(**{k: record.get(k) for k in cls.get_columns().keys()})

    @classmethod
    async def get_by(cls, **filters) -> List[TORMTable]:
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
    async def get_one(cls, **filters) -> TORMTable:
        """It's like get_by except it returns exactly one record or None."""
        return ((await cls.get_by(**filters)) or [None])[0]


    @classmethod
    async def set_initial_version(cls):
        """Sets initial version. 

        Note that unlike DatabaseTable, it will pick the max version available, as the table on creation
        will directly use the latest schema.
        
        """

        if cls.__versions__ is not None:
            max_version = len(cls.__versions__)
        else:
            max_version = max(cls.get_columns().values(), key=lambda c: c.version)
        await Pool.execute("""INSERT INTO versions (table_name, version_num) VALUES ($1,$2)""", cls.__tablename__, max_version)
    

    @classmethod
    async def migrate_to_version(cls, prev_version:int, next_version:int=None):
        """Migrates current table from prev_version up to next_version. (setting next_version=None assumes latest)
        For each Column object, it checks if the version attr is > prev_version, and calls the corresponding alter table
        action to update it.

        If you really need more complex functionality, feel free to override this function, or not use it.

        If __versions__ is set to None, this will get called in db_migrate. Otherwise, this function will not be used.
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

                    if col.alter_tbl is None:
                        await conn.execute(f"ALTER TABLE {cls.__tablename__} ADD COLUMN {col_name} {col.sql};")
                    else:
                        await conn.execute(f"ALTER TABLE {cls.__tablename__} {col.alter_tbl};")
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
