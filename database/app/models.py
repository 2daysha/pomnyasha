from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, BigInteger, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    created_at = Column(TIMESTAMP, server_default=func.now())

class Task(Base):
    __tablename__ = "tasks"
    
    task_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    task_type = Column(String(50))
    duration_minutes = Column(Integer)
    priority = Column(String(20))
    deadline = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.now())