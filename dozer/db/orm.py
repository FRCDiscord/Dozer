from . import DatabaseTable, Pool
from .pqt import Column
from typing import List, Tuple, Dict
import asyncpg



class ORMTable(DatabaseTable):
    """ORM tables are a new variant on DatabaseTables:

    * they are defined from class attributes
    * initial_create, initial_migrate, get_by, delete, and update_or_add (upsert) are handled for you
    * ability to instantiate objects directly from the results of SQL queries

    This class can vastly reduce the amount of boilerplate in a codebase.

    notes: 
     * __uniques__ MUST be a tuple! Do not set it to a string! Runtime will check for this and yell at you!
    """
    __tablename__: str = ''
    __versions__: Tuple[int] = tuple()
    __uniques__: Tuple[str] = tuple()

    _columns: Dict[str, Column] = None


    # Declare the migrate/create functions
    @classmethod
    async def initial_create(cls):
        """Create the table in the database. Already implemented for you. Can still override if desired."""

        if cls is ORMTable:
            # abstract class need not apply
            return

        columns = cls.get_columns()
        # assemble "column = Column('integer not null') into column integer not null, "
        query_params = ", ".join(map(" ".join, zip(columns.keys(), (c.sql for c in columns.values()))))

        if cls.__uniques__:
            # TODO: determine if we should still use __uniques__ or have primary key data in Column
            query_params += f", PRIMARY KEY({', '.join(k for k in cls.__uniques__)})"

        query_str = f"CREATE TABLE {cls.__tablename__}({query_params})"
        async with Pool.acquire() as conn:
            await conn.execute(query_str)


    @classmethod
    async def initial_migrate(cls):
        """Create a version entry in the versions table"""
        if cls is ORMTable:
            # abstract class need not apply
            return

        async with Pool.acquire() as conn:
            await conn.execute("""INSERT INTO versions VALUES ($1, 0)""", cls.__tablename__)

    @staticmethod
    def nullify():
        """Function to be referenced when a table entry value needs to be set to null"""

    def __init__(self, *args, **kwargs):
        # yeah the one drawback of this approach is that you don't get hints for constructors anymore
        # which doesn't stop language servers from somehow figuring out how to do this with dataclasses
        # turns out dataclasses use dark magic 
        # (they dynamically generate and eval an __init__ which they staple onto the class)

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
        
        cls._columns = {name: val for name, val in vars(cls) if isinstance(val, Column)}
        return cls._columns


    @classmethod
    def from_record(cls, record: asyncpg.Record):
        """Converts an asyncpg query record into an instance of the class."""
        if record is None:
            return None

        return cls(**{k: record[k] for k in cls.get_columns().keys()})

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
            records = await conn.fetch(statement, *filters.values())
        return [*map(cls.from_record, records)]
    
    @classmethod
    async def get_one(cls, **filters):
        """It's like get_by except it returns exactly one record or None."""
        return ((await cls.get_by(**filters)) or [None])[0]

    @classmethod
    async def delete(cls, **filters):
        """Deletes by any number of criteria specified as column=value keyword arguments. Returns the number of entries deleted."""
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


# this part isn't super necessary. also need to figure out how to do this without circular imports.

#async def startup_init():
#    """Initializes all ORM classes, and validates them."""
#    for cls in ORMTable.__subclasses__:
#        cls.get_columns()
#        if not isinstance(cls.__uniques__, tuple):
#            raise ValueError(f"{cls}.__uniques__ MUST be a tuple!")
#        
#        if not cls.__tablename__:
#            raise ValueError(f"{cls}.__tablename__ is blank!")