from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from pydantic import BaseModel
import secrets
from datetime import datetime, timezone
from database import get_session
from models import Patient, PatientReadWithAssignments, PatientRead, Psychologist, Message, Assignment
from auth import get_current_user, require_admin, get_current_patient
from logging_utils import log_action

router = APIRouter()

class AssignRequest(BaseModel):
    psychologist_id: int

def generate_access_code():
    return secrets.token_urlsafe(6).upper()

def generate_patient_code():
    return "P-" + secrets.token_hex(2).upper()

@router.post("/patients")
def create_patient(patient: Patient, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # If not admin and no psychologist_id provided, assign to current user
    if current_user.role != "admin" and not patient.psychologist_id:
        patient.psychologist_id = current_user.id

    if not patient.access_code:
        patient.access_code = generate_access_code()
    
    # If psychologist_id is provided, verify it exists
    if patient.psychologist_id:
        psych = session.get(Psychologist, patient.psychologist_id)
        if psych:
            patient.psychologist_name = psych.name
            patient.psychologist_schedule = psych.schedule
            patient.psychologist_photo = psych.photo_url
    else:
        # Fallback: assign to current user
        patient.psychologist_id = current_user.id
        patient.psychologist_name = current_user.name
        patient.psychologist_schedule = current_user.schedule

    session.add(patient)
    session.commit()
    session.refresh(patient)
    
    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "access_code": patient.access_code,
        "email": patient.email,
        "psychologist_id": patient.psychologist_id,
        "psychologist_name": patient.psychologist_name,
        "psychologist_schedule": patient.psychologist_schedule,
        "created_at": patient.created_at,
        "clinical_summary": patient.clinical_summary
    }

@router.get("/patients", response_model=List[PatientReadWithAssignments])
def read_patients(
    offset: int = 0, 
    limit: int = Query(default=100, lte=100), 
    psychologist_id: Optional[int] = None, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    query = select(Patient).options(selectinload(Patient.assignments).selectinload(Assignment.questionnaire))
    
    if current_user.role != "admin":
        query = query.where(Patient.psychologist_id == current_user.id)
    elif psychologist_id:
        query = query.where(Patient.psychologist_id == psychologist_id)
    
    patients = session.exec(query.offset(offset).limit(limit)).all()
    
    results = []
    for p in patients:
        unread_count = session.exec(
            select(func.count(Message.id)).where(
                Message.patient_id == p.id,
                Message.is_from_patient == True,
                Message.read == False
            )
        ).one()
        
        # EXCLUIMOS tanto assignments como is_online para que no choquen
        p_data = p.model_dump(exclude={"assignments", "is_online"})
        
        p_read = PatientReadWithAssignments(
            **p_data,
            is_online=p.is_active_now, # Ahora este es el único valor para is_online
            assignments=p.assignments,
            unread_messages=unread_count
        )
        results.append(p_read)
        
    return results

@router.patch("/patients/{patient_id}/assign")
def assign_patient(patient_id: int, req: AssignRequest, session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    patient = session.get(Patient, patient_id)
    psychologist = session.get(Psychologist, req.psychologist_id)
    
    if not patient or not psychologist:
        raise HTTPException(status_code=404, detail="Patient or Psychologist not found")
        
    patient.psychologist_id = psychologist.id
    patient.psychologist_name = psychologist.name
    patient.psychologist_schedule = psychologist.schedule
    patient.psychologist_photo = psychologist.photo_url
    
    session.add(patient)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "ASSIGN_PATIENT", details={"patient_id": patient.id, "assigned_to": psychologist.email})

    return {"ok": True}

@router.patch("/patients/{patient_id}/clinical-summary")
def update_clinical_summary(
    patient_id: int, 
    summary_data: dict, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    from auth import verify_patient_access
    verify_patient_access(patient_id, current_user, session)
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient.clinical_summary = summary_data.get("clinical_summary", "")
    session.add(patient)
    session.commit()
    session.refresh(patient)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_CLINICAL_SUMMARY", details={"patient_id": patient_id})
    
    return {"ok": True, "clinical_summary": patient.clinical_summary}

@router.get("/patient/me", response_model=PatientRead)
def get_current_patient_profile(
    current_patient: Patient = Depends(get_current_patient)
):
    """Get the current authenticated patient's profile details."""
    return current_patient