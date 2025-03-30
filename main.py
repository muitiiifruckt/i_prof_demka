from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, String, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
import uuid
import random

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./santa.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database models
class GroupDB(Base):
    __tablename__ = "groups"
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    description = Column(String, nullable=True)
    participants = relationship("ParticipantDB", back_populates="group")

class ParticipantDB(Base):
    __tablename__ = "participants"
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    wish = Column(String, nullable=True)
    group_id = Column(String, ForeignKey("groups.id"))
    recipient_id = Column(String, ForeignKey("participants.id"), nullable=True)
    
    group = relationship("GroupDB", back_populates="participants")
    recipient = relationship("ParticipantDB", remote_side=[id])

Base.metadata.create_all(bind=engine)

# Pydantic models
class ParticipantBase(BaseModel):
    name: str
    wish: Optional[str] = None

class ParticipantCreate(ParticipantBase):
    pass

class Participant(ParticipantBase):
    id: str
    recipient: Optional['Participant'] = None

    class Config:
        orm_mode = True

class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None

class GroupCreate(GroupBase):
    pass

class Group(GroupBase):
    id: str
    participants: List[Participant] = []

    class Config:
        orm_mode = True

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

@app.post("/group", status_code=status.H