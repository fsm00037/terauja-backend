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
    patient_id = message.patient_id
    
    psych_id = None
    
    if hasattr(current_user, "role"): # Psychologist
        verify_patient_access(patient_id, current_user, session)
        psych_id = current_user.id
    else: # Patient
        if current_user.id != patient_id:
            raise HTTPException(status_code=403, detail="Access denied")
        # For patient, we attach the message to their CURRENT psychologist
        if current_user.psychologist_id:
            psych_id = current_user.psychologist_id

    db_message = Message.from_orm(message)
    db_message.psychologist_id = psych_id
    
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
    query = select(Message).where(Message.patient_id == patient_id)

    if hasattr(current_user, "role"): # Psychologist
        verify_patient_access(patient_id, current_user, session)
        # Psychologist sees only messages associated with them (or null? let's stick to strict privacy)
        # We only show messages where psychologist_id matches.
        query = query.where(Message.psychologist_id == current_user.id)
    else: # Patient
        if current_user.id != patient_id:
            raise HTTPException(status_code=403, detail="Access denied")
        # Patient implementation:
        # Option A: Patient sees ALL history (standard app behavior).
        # Option B: Patient only sees history with CURRENT psychologist (strict privacy).
        # "esta informacion sera exclusiva entre ellos" - implies the conversation is distinct.
        # If I switch doctors, my chat should likely start empty or relevant to the new doctor.
        # I will filter by the patient's CURRENT psychologist_id to maintain the "exclusive context" approach.
        if current_user.psychologist_id:
             query = query.where(Message.psychologist_id == current_user.psychologist_id)
        else:
             # If no psychologist assigned, maybe show nothing or system messages? 
             # For now, if no psych, maybe show nothing?
             query = query.where(Message.psychologist_id == None) # Or just fail? safe to show empty.

    statement = query.order_by(Message.created_at)
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