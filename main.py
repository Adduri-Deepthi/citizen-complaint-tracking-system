from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

app = FastAPI(
    title="Citizen Complaint Tracker",
    version="1.0.0",
    description="Citizen, Police & Admin Complaint Management System"
)

DATABASE_URL = "sqlite:///./db.sqlite3"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String)

class ComplaintDB(Base):
    __tablename__ = "complaints"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    issue = Column(String)
    location = Column(String)
    status = Column(String)
    filed_at = Column(DateTime)
    last_updated = Column(DateTime)
    history = relationship("StatusUpdateDB", back_populates="complaint")

class StatusUpdateDB(Base):
    __tablename__ = "status_updates"
    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"))
    status = Column(String)
    updated_at = Column(DateTime)
    complaint = relationship("ComplaintDB", back_populates="history")

Base.metadata.create_all(bind=engine)

class UserCreate(BaseModel):
    username: str
    password: str

class MessageOut(BaseModel):
    message: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str

class ComplaintCreate(BaseModel):
    issue: str
    location: str

class StatusUpdateOut(BaseModel):
    status: str
    updated_at: str

class ComplaintOut(BaseModel):
    id: int
    name: str
    issue: str
    location: str
    status: str
    filed_at: str
    last_updated: str
    history: List[StatusUpdateOut]

class AdminDashboardOut(BaseModel):
    total_users: int
    total_citizens: int
    total_police: int
    total_complaints: int
    pending_complaints: int
    resolved_complaints: int
    latest_complaints: List[ComplaintOut]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
tokens = {}

def get_current_user(token: str = Depends(oauth2_scheme)):
    if token not in tokens:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = SessionLocal()
    user = db.query(UserDB).filter(UserDB.username == tokens[token]).first()
    db.close()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@app.post("/register/citizen", response_model=MessageOut)
def register_citizen(user: UserCreate):
    db = SessionLocal()
    if db.query(UserDB).filter(UserDB.username == user.username).first():
        db.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    db.add(UserDB(username=user.username, password=user.password, role="citizen"))
    db.commit()
    db.close()
    return {"message": "Citizen registered successfully"}

@app.post("/register/police", response_model=MessageOut)
def register_police(user: UserCreate):
    db = SessionLocal()
    if db.query(UserDB).filter(UserDB.username == user.username).first():
        db.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    db.add(UserDB(username=user.username, password=user.password, role="police"))
    db.commit()
    db.close()
    return {"message": "Police registered successfully"}

@app.post("/register/admin", response_model=MessageOut)
def register_admin(user: UserCreate):
    db = SessionLocal()
    if db.query(UserDB).filter(UserDB.username == user.username).first():
        db.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    db.add(UserDB(username=user.username, password=user.password, role="admin"))
    db.commit()
    db.close()
    return {"message": "Admin registered successfully"}

@app.post("/token", response_model=TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal()
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    db.close()
    if not user or user.password != form_data.password:
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    token = f"token-{user.username}"
    tokens[token] = user.username
    return {"access_token": token, "token_type": "bearer"}

@app.post("/complaint", response_model=MessageOut)
def file_complaint(data: ComplaintCreate, user: UserDB = Depends(get_current_user)):
    if user.role != "citizen":
        raise HTTPException(status_code=403, detail="Only citizens can file complaints")
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    complaint = ComplaintDB(
        name=user.username,
        issue=data.issue,
        location=data.location,
        status="Pending",
        filed_at=now,
        last_updated=now
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    db.add(StatusUpdateDB(
        complaint_id=complaint.id,
        status="Pending",
        updated_at=now
    ))
    db.commit()
    db.close()
    return {"message": "Complaint filed successfully"}

@app.get("/complaints", response_model=List[ComplaintOut])
def get_complaints(user: UserDB = Depends(get_current_user)):
    db = SessionLocal()
    if user.role == "citizen":
        complaints = db.query(ComplaintDB).filter(ComplaintDB.name == user.username).all()
    else:
        complaints = db.query(ComplaintDB).all()
    result = []
    for c in complaints:
        result.append(ComplaintOut(
            id=c.id,
            name=c.name,
            issue=c.issue,
            location=c.location,
            status=c.status,
            filed_at=str(c.filed_at),
            last_updated=str(c.last_updated),
            history=[StatusUpdateOut(status=h.status, updated_at=str(h.updated_at)) for h in c.history]
        ))
    db.close()
    return result

@app.put("/complaint/{complaint_id}", response_model=MessageOut)
def update_status(complaint_id: int, status: str, user: UserDB = Depends(get_current_user)):
    if user.role != "police":
        raise HTTPException(status_code=403, detail="Only police can update complaints")
    db = SessionLocal()
    complaint = db.query(ComplaintDB).filter(ComplaintDB.id == complaint_id).first()
    if not complaint:
        db.close()
        raise HTTPException(status_code=404, detail="Complaint not found")
    now = datetime.now(timezone.utc)
    complaint.status = status
    complaint.last_updated = now
    db.add(StatusUpdateDB(
        complaint_id=complaint.id,
        status=status,
        updated_at=now
    ))
    db.commit()
    db.close()
    return {"message": "Status updated successfully"}

@app.get("/admin/dashboard", response_model=AdminDashboardOut)
def admin_dashboard(user: UserDB = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access only")
    db = SessionLocal()
    users = db.query(UserDB).all()
    complaints = db.query(ComplaintDB).all()
    latest = db.query(ComplaintDB).order_by(ComplaintDB.filed_at.desc()).limit(5).all()
    dashboard = AdminDashboardOut(
        total_users=len(users),
        total_citizens=len([u for u in users if u.role == "citizen"]),
        total_police=len([u for u in users if u.role == "police"]),
        total_complaints=len(complaints),
        pending_complaints=len([c for c in complaints if c.status == "Pending"]),
        resolved_complaints=len([c for c in complaints if c.status == "Resolved"]),
        latest_complaints=[
            ComplaintOut(
                id=c.id,
                name=c.name,
                issue=c.issue,
                location=c.location,
                status=c.status,
                filed_at=str(c.filed_at),
                last_updated=str(c.last_updated),
                history=[StatusUpdateOut(status=h.status, updated_at=str(h.updated_at)) for h in c.history]
            ) for c in latest
        ]
    )
    db.close()
    return dashboard
