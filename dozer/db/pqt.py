"""Postgres types. Add aliases here."""

class Column:
    """Represents a sql column."""
    def __init__(self, sql: str):
        self.sql: str = sql

Col = Column