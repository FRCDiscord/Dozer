"""Provides database storage for the Dozer Discord bot"""

import sqlalchemy
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, ForeignKeyConstraint, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker

__all__ = ['DatabaseObject', 'Session', 'Column', 'Integer', 'String', 'ForeignKey', 'relationship',
           'Boolean', 'DateTime', 'BigInteger']


class CtxSession(Session):
    """Allows sessions to be used as context managers and asynchronous context managers."""
    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, err_type, err, tb):
        if err_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    async def __aexit__(self, err_type, err, tb):
        return self.__exit__(err_type, err, tb)

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

DatabaseObject = None


def db_init(db_url):
    """Initializes the database connection"""
    global Session
    global DatabaseObject
    engine = sqlalchemy.create_engine(db_url)
    DatabaseObject = declarative_base(bind=engine, name='DatabaseObject')
    DatabaseObject.__table_args__ = {'extend_existing': True}  # allow use of the reload command with db cogs
    Session = sessionmaker(bind=engine, class_=CtxSession)
