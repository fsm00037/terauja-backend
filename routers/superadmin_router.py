from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func, SQLModel
from typing import List, Optional

from database import get_session
from models import Psychologist, Patient, PsychologistRead, PsychologistUpdate
from auth import require_superadmin, hash_password

router = APIRouter()

@router.get("/stats", dependencies=[Depends(require_superadmin)])
async def get_platform_stats(session: Session = Depends(get_session)):
    """Get platform statistics for superadmin dashboard."""
    
    total_psychologists = session.exec(select(func.count(Psychologist.id)).where(Psychologist.role != "superadmin")).one()
    total_patients = session.exec(select(func.count(Patient.id))).one()
    
    # Message stats
    from models import Message
    
    total_messages_psychologist = session.exec(select(func.count(Message.id)).where(Message.is_from_patient == False)).one()
    total_messages_patient = session.exec(select(func.count(Message.id)).where(Message.is_from_patient == True)).one()

    # Online stats
    psychologists_online = session.exec(select(func.count(Psychologist.id)).where(Psychologist.is_online == True).where(Psychologist.role != "superadmin")).one()
    patients_online = session.exec(select(func.count(Patient.id)).where(Patient.is_online == True)).one()
    
    return {
        "total_psychologists": total_psychologists,
        "total_patients": total_patients,
        "online_psychologists": psychologists_online,
        "online_patients": patients_online,
        "total_messages_psychologist": total_messages_psychologist,
        "total_messages_patient": total_messages_patient
    }

class PsychologistCreate(SQLModel):
    name: str
    email: str
    role: str = "psychologist"

@router.post("/users", response_model=PsychologistRead, dependencies=[Depends(require_superadmin)])
async def create_user(
    user_data: PsychologistCreate,
    session: Session = Depends(get_session)
):
    """Create a new user (Psychologist or Admin)."""
    
    # Validate role
    if user_data.role not in ["admin", "psychologist"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be 'admin' or 'psychologist'."
        )
        
    # Check if email exists
    existing_user = session.exec(select(Psychologist).where(Psychologist.email == user_data.email)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
        
    # Generate random password
    import secrets
    from utils.sender import send_credentials_email
    
    raw_password = secrets.token_urlsafe(8)
    
    # Create Psychologist instance
    new_user = Psychologist(
        name=user_data.name,
        email=user_data.email,
        role=user_data.role,
        password=hash_password(raw_password),
        schedule="Lunes a Viernes, 9:00 - 18:00"
    )
    
    # Send credentials via email
    send_credentials_email(user_data.email, raw_password)
    
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    return new_user

@router.get("/users", response_model=List[PsychologistRead], dependencies=[Depends(require_superadmin)])
async def list_users(
    session: Session = Depends(get_session)
):
    """List all psychologists and admins."""
    users = session.exec(select(Psychologist)).all()
    return users
