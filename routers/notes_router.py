from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import Note, NoteRead, Psychologist
from auth import get_current_user, verify_patient_access
from logging_utils import log_action

router = APIRouter()

@router.post("", response_model=NoteRead)
def create_note(
    note: Note, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(note.patient_id, current_user, session)
    session.add(note)
    session.commit()
    session.refresh(note)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "CREATE_NOTE", 
        details={"patient_id": note.patient_id, "title": note.title}
    )
    
    return note

@router.get("/{patient_id}", response_model=List[NoteRead])
def get_notes(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(patient_id, current_user, session)
    statement = select(Note).where(Note.patient_id == patient_id).order_by(Note.created_at.desc())
    return session.exec(statement).all()

@router.delete("/{note_id}")
def delete_note(
    note_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    verify_patient_access(note.patient_id, current_user, session)
    session.delete(note)
    session.commit()
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "DELETE_NOTE", 
        details={"note_id": note_id}
    )
    
    return {"ok": True}