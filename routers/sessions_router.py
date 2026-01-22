from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import Session as TherapySession, SessionRead, SessionUpdate, Psychologist
from auth import get_current_user, verify_patient_access
from logging_utils import log_action

router = APIRouter()

@router.post("", response_model=SessionRead)
def create_session(
    session_data: TherapySession, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(session_data.patient_id, current_user, session)
    
    # Set the psychologist_id to the current user
    session_data.psychologist_id = current_user.id
    
    session.add(session_data)
    session.commit()
    session.refresh(session_data)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "CREATE_SESSION", 
        details={"patient_id": session_data.patient_id, "date": session_data.date}
    )
    
    return session_data

@router.get("/{patient_id}", response_model=List[SessionRead])
def get_sessions(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(patient_id, current_user, session)
    
    # Filter by both patient_id AND psychologist_id
    statement = select(TherapySession).where(
        TherapySession.patient_id == patient_id,
        TherapySession.psychologist_id == current_user.id
    ).order_by(TherapySession.date.desc())
    
    return session.exec(statement).all()

@router.put("/{session_id}", response_model=SessionRead)
def update_session(
    session_id: int, 
    session_data: SessionUpdate, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    verify_patient_access(db_session.patient_id, current_user, session)
    
    if session_data.date: db_session.date = session_data.date
    if session_data.duration: db_session.duration = session_data.duration
    if session_data.description: db_session.description = session_data.description
    if session_data.notes: db_session.notes = session_data.notes
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "UPDATE_SESSION", 
        details={"session_id": session_id}
    )
    
    return db_session

@router.delete("/{session_id}")
def delete_session(
    session_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    verify_patient_access(db_session.patient_id, current_user, session)
    
    session.delete(db_session)
    session.commit()
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "DELETE_SESSION", 
        details={"session_id": session_id}
    )
    
    return {"ok": True}