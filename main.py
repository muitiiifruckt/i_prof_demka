from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, String, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session, joinedload
import uuid
import random

# Database setup
SQLALCHEMY_DATABASE_URL = "postgresql://santa:secret@db:5432/santadb"
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

class ParticipantLite(BaseModel):
    id: str
    name: str
    wish: Optional[str] = None
    
    class Config:
        orm_mode = True

class Participant(ParticipantLite):
    recipient: Optional[ParticipantLite] = None
    
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

def serialize_participant(participant: ParticipantDB) -> dict:
    return {
        "id": participant.id,
        "name": participant.name,
        "wish": participant.wish,
        "recipient": {
            "id": participant.recipient.id,
            "name": participant.recipient.name,
            "wish": participant.recipient.wish
        } if participant.recipient else None
    }

@app.post("/group", status_code=status.HTTP_201_CREATED)
def create_group(group_data: GroupCreate, db: Session = Depends(get_db)):
    group_id = str(uuid.uuid4())
    db_group = GroupDB(id=group_id, **group_data.dict())
    db.add(db_group)
    db.commit()
    return {"id": group_id}

@app.get("/groups", response_model=List[Group])
def get_groups(db: Session = Depends(get_db)):
    groups = db.query(GroupDB).all()
    return [{
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "participants": []
    } for group in groups]

@app.get("/group/{group_id}", response_model=Group)
def get_group(group_id: str, db: Session = Depends(get_db)):
    group = db.query(GroupDB)\
        .options(joinedload(GroupDB.participants).joinedload(ParticipantDB.recipient))\
        .filter(GroupDB.id == group_id)\
        .first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "participants": [serialize_participant(p) for p in group.participants]
    }

@app.put("/group/{group_id}")
def update_group(group_id: str, group_data: GroupCreate, db: Session = Depends(get_db)):
    group = db.query(GroupDB).filter(GroupDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    group.name = group_data.name
    group.description = group_data.description
    db.commit()
    return {"message": "Group updated"}

@app.delete("/group/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: str, db: Session = Depends(get_db)):
    group = db.query(GroupDB).filter(GroupDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    db.delete(group)
    db.commit()

@app.post("/group/{group_id}/participant", status_code=status.HTTP_201_CREATED)
def add_participant(group_id: str, participant_data: ParticipantCreate, db: Session = Depends(get_db)):
    group = db.query(GroupDB).filter(GroupDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    participant_id = str(uuid.uuid4())
    db_participant = ParticipantDB(
        id=participant_id,
        **participant_data.dict(),
        group_id=group_id
    )
    db.add(db_participant)
    db.commit()
    return {"id": participant_id}

@app.delete("/group/{group_id}/participant/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_participant(group_id: str, participant_id: str, db: Session = Depends(get_db)):
    participant = db.query(ParticipantDB).filter(
        ParticipantDB.id == participant_id,
        ParticipantDB.group_id == group_id
    ).first()
    
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    db.delete(participant)
    db.commit()

@app.post("/group/{group_id}/toss", response_model=List[Participant])
def toss(group_id: str, db: Session = Depends(get_db)):
    group = db.query(GroupDB)\
        .options(joinedload(GroupDB.participants))\
        .filter(GroupDB.id == group_id)\
        .first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    participants = group.participants
    if len(participants) < 3:
        raise HTTPException(status_code=409, detail="Not enough participants")
    
    participant_ids = [p.id for p in participants]
    
    # Generate valid permutation
    while True:
        shuffled_ids = random.sample(participant_ids, len(participant_ids))
        if all(a != b for a, b in zip(participant_ids, shuffled_ids)):
            break
    
    # Update recipients
    for participant, recipient_id in zip(participants, shuffled_ids):
        participant.recipient_id = recipient_id
    
    db.commit()
    
    # Return serialized participants
    return [serialize_participant(p) for p in participants]

@app.get("/group/{group_id}/participant/{participant_id}/recipient", response_model=ParticipantLite)
def get_recipient(group_id: str, participant_id: str, db: Session = Depends(get_db)):
    participant = db.query(ParticipantDB)\
        .options(joinedload(ParticipantDB.recipient))\
        .filter(
            ParticipantDB.id == participant_id,
            ParticipantDB.group_id == group_id
        )\
        .first()
    
    if not participant or not participant.recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    
    return participant.recipient

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)