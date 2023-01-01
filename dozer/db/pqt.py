"""Postgres types. Add aliases here."""

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
