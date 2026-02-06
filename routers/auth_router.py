from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime, timezone
from pydantic import BaseModel

from database import get_session
from models import Psychologist, Patient
from auth import hash_password, verify_password, create_access_token, get_current_actor, get_current_patient
from logging_utils import log_action

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

class PatientLoginRequest(BaseModel):
    patient_code: str
    access_code: str

@router.post("/login")
def login(creds: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(Psychologist).where(Psychologist.email == creds.email)).first()
    if not user or not verify_password(creds.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create JWT token
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    
    # Log successful login
    log_action(session, user.id, "psychologist", user.name, "LOGIN", details="Successful login")
    
    # Set online status
    user.is_online = True
    user.last_active = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)

    return {
        "id": user.id, 
        "name": user.name, 
        "role": user.role, 
        "email": user.email,
        "access_token": access_token
    }

@router.post("/auth")
def authenticate_patient(login: PatientLoginRequest, session: Session = Depends(get_session)):
    statement = select(Patient).where(
        Patient.access_code == login.access_code,
        Patient.patient_code == login.patient_code
    )
    patient = session.exec(statement).first()
    if not patient:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate Token
    access_token = create_access_token(data={
        "sub": str(patient.id), 
        "role": "patient",
        "token_version": patient.token_version
    })

    # Set online status
    patient.is_online = True
    patient.last_active = datetime.now(timezone.utc)
    session.add(patient)
    session.commit()
    session.refresh(patient)
    
    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "access_code": patient.access_code,
        "psychologist_id": patient.psychologist_id,
        "psychologist_name": patient.psychologist_name,
        "psychologist_schedule": patient.psychologist_schedule,
        "access_token": access_token
    }

@router.post("/logout")
def logout(session: Session = Depends(get_session), current_user = Depends(get_current_actor)):
    if hasattr(current_user, "role"): # Psychologist
        current_user.is_online = False
        session.add(current_user)
        log_action(session, current_user.id, "psychologist", current_user.name, "LOGOUT")
    else: # Patient
        current_user.is_online = False
        session.add(current_user)
    
    session.commit()
    return {"ok": True}

@router.post("/heartbeat")
def heartbeat(session: Session = Depends(get_session), current_user = Depends(get_current_actor)):
    now = datetime.now(timezone.utc)
    
    # Calculate delta if previously active and within reasonable "session" window (e.g., < 2 mins)
    delta = 0
    if current_user.is_online and current_user.last_active:
        # Ensure last_active is timezone-aware
        last_active = current_user.last_active
        if last_active.tzinfo is None:
            # If naive, assume it's UTC
            last_active = last_active.replace(tzinfo=timezone.utc)
        
        diff = (now - last_active).total_seconds()
        if diff < 120: # If heartbeat is regular (e.g. every 60s), add diff. If huge gap, assume new session.
            delta = int(diff)
            
    if hasattr(current_user, "role"): # Psychologist
        current_user.last_active = now
        current_user.is_online = True
        current_user.total_online_seconds += delta
        session.add(current_user)
    else: # Patient
        current_user.last_active = now
        current_user.is_online = True
        current_user.total_online_seconds += delta
        session.add(current_user)
    
    session.commit()
    return {"ok": True}

@router.get("/patient/status")
def get_patient_status(
    session: Session = Depends(get_session),
    current_patient: Patient = Depends(get_current_patient)
):
    psychologist_online = False
    if current_patient.psychologist_id:
        psychologist = session.get(Psychologist, current_patient.psychologist_id)
        if psychologist:
            # Solo llamamos a la propiedad que creamos
            psychologist_online = psychologist.is_active_now
            
            # Limpieza reactiva opcional: si la propiedad dice False pero la DB dice True
            if not psychologist_online and psychologist.is_online:
                psychologist.is_online = False
                session.add(psychologist)
                session.commit()

    return {
        "is_online": current_patient.is_active_now,
        "psychologist_is_online": psychologist_online
    }