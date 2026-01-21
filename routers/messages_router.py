from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import Message, MessageCreate, MessageRead, Psychologist
from auth import get_current_user, get_current_actor, verify_patient_access
from logging_utils import log_action

router = APIRouter()

@router.post("", response_model=MessageRead)
def create_message(
    message: MessageCreate, 
    session: Session = Depends(get_session), 
    current_user = Depends(get_current_actor)
):
    # Verify access based on user type
    if hasattr(current_user, "role"): # Psychologist
        verify_patient_access(message.patient_id, current_user, session)
    else: # Patient
        if current_user.id != message.patient_id:
            raise HTTPException(status_code=403, detail="Access denied")

    db_message = Message.from_orm(message)
    session.add(db_message)
    session.commit()
    session.refresh(db_message)
    
    log_action(
        session, current_user.id, 
        "psychologist" if not message.is_from_patient else "patient", 
        current_user.name, "CREATE_MESSAGE", 
        details={"patient_id": message.patient_id, "is_from_patient": message.is_from_patient}
    )
    
    return db_message

@router.get("/{patient_id}", response_model=List[MessageRead])
def get_messages(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user = Depends(get_current_actor)
):
    # Verify access based on user type
    if hasattr(current_user, "role"): # Psychologist
        verify_patient_access(patient_id, current_user, session)
    else: # Patient
        if current_user.id != patient_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    statement = select(Message).where(Message.patient_id == patient_id).order_by(Message.created_at)
    return session.exec(statement).all()

@router.post("/mark-read/{patient_id}")
def mark_messages_read(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(patient_id, current_user, session)
    statement = select(Message).where(
        Message.patient_id == patient_id,
        Message.is_from_patient == True,
        Message.read == False
    )
    messages = session.exec(statement).all()
    
    for msg in messages:
        msg.read = True
        session.add(msg)
        
    session.commit()
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "MARK_MESSAGES_READ", 
        details={"patient_id": patient_id, "count": len(messages)}
    )
    
    return {"ok": True, "count": len(messages)}

@router.delete("/{patient_id}")
def delete_messages(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(patient_id, current_user, session)
    statement = select(Message).where(Message.patient_id == patient_id)
    results = session.exec(statement)
    for message in results:
        session.delete(message)
    session.commit()
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "DELETE_MESSAGES", 
        details={"patient_id": patient_id}
    )
    
    return {"ok": True, "deleted": True}