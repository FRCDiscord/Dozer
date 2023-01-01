"""Postgres types. Add aliases here."""

class Column:
    """Represents a sql column.
    Includes an optional version parameter for columsn added later.
    """
    def __init__(self, sql: str, version=0):
        self.sql: str = sql
        self.version: int = version

Col = Column
