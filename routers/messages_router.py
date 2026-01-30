from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import Message, MessageCreate, MessageRead, Psychologist
from auth import get_current_user, get_current_actor, verify_patient_access
from logging_utils import log_action
from services.firebase_service import send_push_to_patient

router = APIRouter()

@router.post("", response_model=MessageRead)
def create_message(
    message: MessageCreate, 
    session: Session = Depends(get_session), 
    current_user = Depends(get_current_actor)
):
    # 1. Identificación segura del "Actor" para el log
    # Si es psicólogo usa .name, si es paciente usa .patient_code
    actor_name = getattr(current_user, "name", getattr(current_user, "patient_code", "Unknown"))
    actor_type = "psychologist" if hasattr(current_user, "role") else "patient"

    # 2. Verificar acceso y determinar psych_id
    patient_id = message.patient_id
    psych_id = None
    
    if actor_type == "psychologist":
        verify_patient_access(patient_id, current_user, session)
        psych_id = current_user.id
    else:
        if current_user.id != patient_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if current_user.psychologist_id:
            psych_id = current_user.psychologist_id

    # 3. Crear el mensaje con los campos de trazabilidad de IA
    db_message = Message(
        content=message.content,
        patient_id=message.patient_id,
        is_from_patient=message.is_from_patient,
        psychologist_id=psych_id,
        # Registramos si vino de una IA
        ai_suggestion_log_id=message.ai_suggestion_log_id,
        used_ai_suggestion=True if message.ai_suggestion_log_id else False,
        was_edited_by_human=message.was_edited_by_human,
    )
    
    session.add(db_message)
    session.commit()
    session.refresh(db_message)

    # 4. (Opcional) Vincular el Log de IA con el mensaje final
    if message.ai_suggestion_log_id:
        from models import AISuggestionLog
        ai_log = session.get(AISuggestionLog, message.ai_suggestion_log_id)
        if ai_log:
            ai_log.final_option_id = message.selected_option
            session.add(ai_log)
            session.commit()
    

    log_action(
        session, 
        current_user.id, 
        actor_type, 
        actor_name, 
        "CREATE_MESSAGE", 
        details={
            "patient_id": message.patient_id, 
            "is_from_patient": message.is_from_patient,
            "ai_used": bool(message.ai_suggestion_log_id)
        }
    )
    

    # Notify patient if message is from psychologist
    if not message.is_from_patient:
        try:
            # Get psychologist name for better notification
            psych_name = "Tu psicólogo"
            if hasattr(current_user, "name"):
                psych_name = current_user.name
                
            from services.firebase_service import send_new_message_notification
            send_new_message_notification(
                patient_id=message.patient_id,
                message_id=db_message.id,
                sender_name=psych_name
            )
        except Exception as e:
            print(f"Error sending notification: {e}")

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
        query = query.where(Message.psychologist_id == current_user.id)
    else: # Patient
        if current_user.id != patient_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if current_user.psychologist_id:
             query = query.where(Message.psychologist_id == current_user.psychologist_id)
        else:
             query = query.where(Message.psychologist_id == None) 

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