import sqlalchemy
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker

__all__ = ['engine', 'DatabaseObject', 'Session', 'Column', 'Integer', 'String', 'ForeignKey', 'relationship']

engine = sqlalchemy.create_engine('sqlite:///dozer.db')
DatabaseObject = declarative_base(bind=engine, name='DatabaseObject')

class CtxSession(Session):
	def __enter__(self):
		return self
	
	def __exit__(self, err_type, err, tb):
		if err_type is None:
			self.commit()
		else:
			self.rollback()
		return False

Session = sessionmaker(bind=engine, class_=CtxSession)
