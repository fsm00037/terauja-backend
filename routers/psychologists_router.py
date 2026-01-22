from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
import secrets

from database import get_session
from models import Psychologist, PsychologistRead, PsychologistUpdate, Patient
from auth import hash_password, require_admin, get_current_user
from logging_utils import log_action
from utils.sender import send_credentials_email

router = APIRouter()

@router.get("/psychologists", response_model=List[PsychologistRead])
def get_psychologists(session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    return session.exec(select(Psychologist).where(Psychologist.role != "superadmin")).all()

@router.post("/psychologists")
def create_psychologist(psychologist: Psychologist, session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    # Generate random password
    raw_password = secrets.token_urlsafe(8)
    psychologist.password = hash_password(raw_password)
    
    # Send credentials via email
    send_credentials_email(psychologist.email, raw_password)
    
    session.add(psychologist)
    session.commit()
    session.refresh(psychologist)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "CREATE_PSYCHOLOGIST", details={"created_email": psychologist.email, "role": psychologist.role})

    return {
        "id": psychologist.id,
        "name": psychologist.name,
        "email": psychologist.email,
        "role": psychologist.role,
        "schedule": psychologist.schedule,
        "phone": psychologist.phone
    }

@router.delete("/psychologists/{user_id}")
def delete_psychologist(user_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Unassign patients
    patients = session.exec(select(Patient).where(Patient.psychologist_id == user_id)).all()
    for p in patients:
        p.psychologist_id = None
        p.psychologist_name = "Sin Asignar"
        p.psychologist_schedule = ""
        session.add(p)
        
    session.delete(user)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_PSYCHOLOGIST", details={"deleted_user_id": user_id})
    
    return {"ok": True}

@router.get("/profile/{user_id}", response_model=PsychologistRead)
def get_user_profile(user_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # Users can only access their own profile unless admin
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/profile/{user_id}", response_model=PsychologistRead)
def update_user_profile(user_id: int, profile_data: PsychologistUpdate, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # Users can only update their own profile unless admin
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if profile_data.name: user.name = profile_data.name
    if profile_data.schedule: user.schedule = profile_data.schedule
    if profile_data.phone: user.phone = profile_data.phone
    if profile_data.ai_style is not None: user.ai_style = profile_data.ai_style
    if profile_data.ai_tone is not None: user.ai_tone = profile_data.ai_tone
    if profile_data.ai_instructions is not None: user.ai_instructions = profile_data.ai_instructions
        
    session.add(user)
    
    # Propagate changes to assigned patients
    patients = session.exec(select(Patient).where(Patient.psychologist_id == user_id)).all()
    for p in patients:
        if profile_data.name: p.psychologist_name = profile_data.name
        if profile_data.schedule: p.psychologist_schedule = profile_data.schedule
        session.add(p)
        
    session.commit()
    session.refresh(user)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_PROFILE", details={"updated_user_id": user_id})
    
    return user