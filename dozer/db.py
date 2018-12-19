"""Provides database storage for the Dozer Discord bot"""

import sqlalchemy
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, ForeignKeyConstraint, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker
import asyncpg

__all__ = ['Session', 'Column', 'Integer', 'String', 'ForeignKey', 'relationship',
           'Boolean', 'DateTime', 'BigInteger']


async def db_init(db_url):
    """Initializes the database connection"""
    # global Session
    # global DatabaseObject
    # engine = sqlalchemy.create_engine(db_url)
    # DatabaseObject = declarative_base(bind=engine, name='DatabaseObject')
    # DatabaseObject.__table_args__ = {'extend_existing': True}  # allow use of the reload command with db cogs
    # Session = sessionmaker(bind=engine, class_=CtxSession)
    global Pool
    Pool = await asyncpg.create_pool(dsn=db_url, command_timeout=15)


class DatabaseTable:
    __tablename__ = None

    # Declare the migrate/create functions
    async def initial_create(self):
        """Create the table in the database with just the ID field. Overwrite this field in your subclasses with your
        full schema. Make sure your DB rows have the exact same name as the python variable names."""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {self.__tablename__} (
            id serial PRIMARY KEY
            )""")

    __versions__ = {initial_create}

    __uniques__ = ["id"]

    def __init__(self, passed_id=None):
        self.id = passed_id

    async def update_or_add(self):
        keys = []
        values = []
        for var, value in self.__dict__.items():
            # Done so that the two are guaranteed to be in the same order, which isn't true of keys() and values()
            keys.append(var)
            values.append(value)
        updates = ""
        for key in keys:
            if key in self.__uniques__:
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
            ON CONFLICT ({", ".join(keys)}) DO UPDATE
            SET {updates}
            """, values)

    def __repr__(self):
        return f"{self.__tablename__}: <Id: {self.id}>"

    @classmethod
    async def get_by_id(cls, obj_id):
        """Get an instance of this object by it's primary key, id. This function will work for most subclasses."""
        async with Pool.acquire() as conn:  # Use transaction here?
            stmt = await conn.prepare(f"""SELECT * FROM {cls.__tablename__} WHERE id = ?""")
            result = stmt.fetchrow(obj_id)
            obj = cls()
            for var in cls().__dict__:
                setattr(obj, var, result.get(var))
            return obj


class GuildTable(DatabaseTable):
    async def initial_create(self):
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {self.__tablename__} (
            id serial PRIMARY KEY,
            guild_id BIGINT,
            )""")

    def __init__(self, obj_id=None, guild_id=None):
        super().__init__(obj_id)
        self.guild_id = guild_id
