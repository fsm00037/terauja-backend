from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import List

from database import get_session, engine
from models import Session as TherapySession, SessionRead, SessionUpdate, Psychologist, Patient
from auth import get_current_user, verify_patient_access
from logging_utils import log_action
from utils.logger import logger
from llm_service import generate_session_summary, generate_bitacora_summary
import asyncio

router = APIRouter()

async def background_generate_session_summary(session_id: int, chat_snapshot: list):
    try:
        summary = await generate_session_summary(chat_snapshot)
        with Session(engine) as db:
            db_session = db.get(TherapySession, session_id)
            if db_session:
                db_session.ai_summary = summary
                
                # Generate a brief summary for the clinical log using Gemma
                bitacora_entry_content = await generate_bitacora_summary(
                    db_session.description, 
                    db_session.notes, 
                    summary
                )
                
                # Append or Update Patient's clinical_log
                patient = db.get(Patient, db_session.patient_id)
                if patient:
                    date_str = db_session.date.strftime("%d/%m/%Y")
                    sid_tag = f"### SID:{session_id} | "
                    log_entry = f"{sid_tag}{date_str} - {db_session.description}\n{bitacora_entry_content}\n\n"
                    
                    if not patient.clinical_log:
                        patient.clinical_log = log_entry
                    else:
                        # Check if an entry with this SID already exists to replace it
                        if sid_tag in patient.clinical_log:
                            # Split by '### SID:' to find and replace the specific entry
                            parts = patient.clinical_log.split("### SID:")
                            new_parts = []
                            for p in parts:
                                if not p.strip(): continue
                                if p.startswith(f"{session_id} | "):
                                    # This is the entry to replace
                                    new_parts.append(log_entry.replace("### SID:", ""))
                                else:
                                    new_parts.append(p)
                            patient.clinical_log = "### SID:" + "### SID:".join(new_parts)
                        else:
                            # If not found, check if it was an old entry without SID (by date and title)
                            old_header = f"### Sesión {date_str} - {db_session.description}"
                            if old_header in patient.clinical_log:
                                patient.clinical_log = patient.clinical_log.replace(old_header, log_entry.strip())
                            else:
                                # Just append
                                if patient.clinical_log and not patient.clinical_log.endswith("\n\n"):
                                    patient.clinical_log += "\n\n"
                                patient.clinical_log += log_entry
                    
                    db.add(patient)
                
                db.add(db_session)
                db.commit()
                logger.info(f"AI summary saved for session {session_id} and appended to clinical log")
    except Exception as e:
        logger.error(f"Failed to generate summary for session {session_id}: {e}")


@router.post("", response_model=SessionRead)
def create_session(
    session_data: TherapySession, 
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(session_data.patient_id, current_user, session)
    
    # Set the psychologist_id to the current user
    session_data.psychologist_id = current_user.id
    
    session.add(session_data)
    session.commit()
    session.refresh(session_data)
    
    if session_data.chat_snapshot:
        background_tasks.add_task(background_generate_session_summary, session_data.id, session_data.chat_snapshot)

    
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
        TherapySession.psychologist_id == current_user.id,
        TherapySession.deleted_at == None
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
    if not db_session or db_session.deleted_at:
        raise HTTPException(status_code=404, detail="Session not found")
    
    verify_patient_access(db_session.patient_id, current_user, session)
    
    update_data = session_data.dict(exclude_unset=True)
    
    for key, value in update_data.items():
        if key != "chat_snapshot":
            setattr(db_session, key, value)
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    return db_session

@router.delete("/{session_id}")
def delete_session(
    session_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    from datetime import datetime, timezone
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    verify_patient_access(db_session.patient_id, current_user, session)
    
    db_session.deleted_at = datetime.now(timezone.utc)
    session.add(db_session)
    session.commit()
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "DELETE_SESSION", 
        details={"session_id": session_id}
    )
    
    return {"ok": True}

@router.post("/{session_id}/regenerate-summary")
def regenerate_session_summary_endpoint(
    session_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: Psychologist = Depends(get_current_user)
):
    db_session = session.get(TherapySession, session_id)
    if not db_session or db_session.deleted_at:
        raise HTTPException(status_code=404, detail="Session not found")
    
    verify_patient_access(db_session.patient_id, current_user, session)
    
    if not db_session.chat_snapshot:
        raise HTTPException(status_code=400, detail="No chat history available for this session")
    
    # Clear current summary so frontend can show loading state
    db_session.ai_summary = None
    session.add(db_session)
    session.commit()
    
    background_tasks.add_task(background_generate_session_summary, session_id, db_session.chat_snapshot)
    
    return {"ok": True}

@router.post("/{session_id}/regenerate-bitacora")
async def regenerate_bitacora_entry(
    session_id: int,
    session: Session = Depends(get_session),
    current_user: Psychologist = Depends(get_current_user)
):
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify access
    patient = session.get(Patient, db_session.patient_id)
    if current_user.role != "admin" and patient.psychologist_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not db_session.ai_summary:
        raise HTTPException(status_code=400, detail="Session has no AI summary. Generate summary first.")

    # Generate new entry content
    bitacora_entry_content = await generate_bitacora_summary(
        db_session.description, 
        db_session.notes, 
        db_session.ai_summary
    )
    
    date_str = db_session.date.strftime("%d/%m/%Y")
    sid_tag = f"### SID:{session_id} | "
    log_entry = f"{sid_tag}{date_str} - {db_session.description}\n{bitacora_entry_content}\n\n"
    
    if not patient.clinical_log:
        patient.clinical_log = log_entry
    else:
        if sid_tag in patient.clinical_log:
            parts = patient.clinical_log.split("### SID:")
            new_parts = []
            for p in parts:
                if not p.strip(): continue
                if p.startswith(f"{session_id} | "):
                    new_parts.append(log_entry.replace("### SID:", ""))
                else:
                    new_parts.append(p)
            patient.clinical_log = "### SID:" + "### SID:".join(new_parts)
        else:
            # Check old format
            old_header = f"### Sesión {date_str} - {db_session.description}"
            if old_header in patient.clinical_log:
                patient.clinical_log = patient.clinical_log.replace(old_header, log_entry.strip())
            else:
                if not patient.clinical_log.endswith("\n\n"):
                    patient.clinical_log += "\n\n"
                patient.clinical_log += log_entry
    
    session.add(patient)
    session.commit()
    
    return {"ok": True, "clinical_log": patient.clinical_log}
