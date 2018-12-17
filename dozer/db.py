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


DatabaseObject = None


def db_init(db_url):
    """Initializes the database connection"""
    global Session
    global DatabaseObject
    engine = sqlalchemy.create_engine(db_url)
    DatabaseObject = declarative_base(bind=engine, name='DatabaseObject')
    DatabaseObject.__table_args__ = {'extend_existing': True}  # allow use of the reload command with db cogs
    Session = sessionmaker(bind=engine, class_=CtxSession)
