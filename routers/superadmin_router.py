from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func, SQLModel
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from database import get_session
from models import Psychologist, Patient, PsychologistRead
from auth import require_superadmin, hash_password

router = APIRouter()

@router.get("/stats", dependencies=[Depends(require_superadmin)])
async def get_platform_stats(session: Session = Depends(get_session)):
    """Get platform statistics for superadmin dashboard."""
    
    total_psychologists = session.exec(select(func.count(Psychologist.id)).where(Psychologist.role != "superadmin")).one()
    total_patients = session.exec(select(func.count(Patient.id))).one()
    
    # Message stats
    from models import Message, Session as TherapySession
    
    messages = session.exec(select(Message)).all()
    total_messages_psychologist = sum(1 for m in messages if not m.is_from_patient)
    total_messages_patient = sum(1 for m in messages if m.is_from_patient)
    total_words = sum(len(m.content.split()) for m in messages if m.content)

    # Add messages from Session.chat_snapshot
    sessions = session.exec(select(TherapySession)).all()
    for s in sessions:
        if s.chat_snapshot:
            for msg in s.chat_snapshot:
                if msg.get("sender") == "patient":
                    total_messages_patient += 1
                elif msg.get("sender") == "therapist":
                    total_messages_psychologist += 1
                
                text = msg.get("text")
                if isinstance(text, str):
                    total_words += len(text.split())

    # Online stats
    now_utc = datetime.utcnow()
    active_limit = now_utc - timedelta(seconds=120)

    psychologists_online = session.exec(
        select(func.count(Psychologist.id))
        .where(Psychologist.role != "superadmin")
        .where(Psychologist.is_online == True)
        .where(Psychologist.last_active >= active_limit)
    ).one()
    
    patients_online = session.exec(
        select(func.count(Patient.id))
        .where(Patient.is_online == True)
        .where(Patient.last_active >= active_limit)
    ).one()
    
    return {
        "total_psychologists": total_psychologists,
        "total_patients": total_patients,
        "online_psychologists": psychologists_online,
        "online_patients": patients_online,
        "total_messages_psychologist": total_messages_psychologist,
        "total_messages_patient": total_messages_patient,
        "total_words": total_words
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

@router.get("/stats/daily-messages", dependencies=[Depends(require_superadmin)])
async def get_daily_message_stats(session: Session = Depends(get_session)):
    """Get total messages per day for the last 30 days."""
    from datetime import datetime, timedelta
    from models import Message, Session as TherapySession
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    messages = session.exec(select(Message).where(Message.created_at >= thirty_days_ago)).all()
    sessions = session.exec(select(TherapySession).where(TherapySession.date >= thirty_days_ago)).all()
    
    stats = {}
    
    # Initialize last 30 days
    for i in range(31):
        date = (thirty_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        stats[date] = {"date": date, "patient_count": 0, "psychologist_count": 0}
        
    for msg in messages:
        date_str = msg.created_at.strftime("%Y-%m-%d")
        if date_str in stats:
            if msg.is_from_patient:
                stats[date_str]["patient_count"] += 1
            else:
                stats[date_str]["psychologist_count"] += 1

    for s in sessions:
        if s.chat_snapshot:
            date_str = s.date.strftime("%Y-%m-%d")
            if date_str in stats:
                for msg in s.chat_snapshot:
                    if msg.get("sender") == "patient":
                        stats[date_str]["patient_count"] += 1
                    elif msg.get("sender") == "therapist":
                        stats[date_str]["psychologist_count"] += 1
                
    return list(stats.values())

@router.get("/users/detailed", dependencies=[Depends(require_superadmin)])
async def get_detailed_users(session: Session = Depends(get_session)):
    """Get detailed lists of users with calculated stats."""
    from models import Message, Session as TherapySession, AISuggestionLog
    from sqlalchemy.orm import selectinload
    
    # 1. Fetch all needed data
    psychologists = session.exec(select(Psychologist).where(Psychologist.role != "superadmin").options(selectinload(Psychologist.patients))).all()
    patients = session.exec(select(Patient).options(selectinload(Patient.psychologist))).all()
    
    # Fetch all sessions for efficient filtering
    all_sessions = session.exec(select(TherapySession)).all()
    
    # 2. Process Psychologists
    psych_list = []
    for psych in psychologists:
        # Count patients
        patient_count = len(psych.patients)
        
        # Count sessions
        psych_sessions = [s for s in all_sessions if s.psychologist_id == psych.id]
        session_count = len(psych_sessions)
        
        # Count AI Clicks
        ai_clicks = session.exec(select(func.count(AISuggestionLog.id)).where(AISuggestionLog.psychologist_id == psych.id).where(AISuggestionLog.final_option_id != None)).one()
        
        # Count Messages & Words
        messages = session.exec(select(Message).where(Message.psychologist_id == psych.id).where(Message.is_from_patient == False)).all()
        msg_count = len(messages)
        word_count = sum(len(m.content.split()) for m in messages)
        
        for s in psych_sessions:
            if s.chat_snapshot:
                for msg in s.chat_snapshot:
                    if msg.get("sender") == "therapist" and isinstance(msg.get("text"), str):
                        msg_count += 1
                        word_count += len(msg["text"].split())
        
        psych_list.append({
            "id": psych.id,
            "name": psych.name,
            "email": psych.email,
            "role": psych.role,
            "is_online": psych.is_active_now,
            "patients_count": patient_count,
            "sessions_count": session_count,
            "ai_clicks": ai_clicks,
            "message_count": msg_count,
            "word_count": word_count,
            "last_active": psych.last_active
        })
        
    # 3. Process Patients
    patient_list = []
    for pat in patients:
        # Count Messages & Words
        messages = session.exec(select(Message).where(Message.patient_id == pat.id).where(Message.is_from_patient == True)).all()
        msg_count = len(messages)
        word_count = sum(len(m.content.split()) for m in messages)
        
        pat_sessions = [s for s in all_sessions if s.patient_id == pat.id]
        for s in pat_sessions:
            if s.chat_snapshot:
                for msg in s.chat_snapshot:
                    if msg.get("sender") == "patient" and isinstance(msg.get("text"), str):
                        msg_count += 1
                        word_count += len(msg["text"].split())
        
        psych_name = pat.psychologist.name if pat.psychologist else "Sin asignar"
        
        patient_list.append({
            "id": pat.id,
            "patient_code": pat.patient_code,
            "psychologist_name": psych_name,
            "is_online": pat.is_active_now,
            "message_count": msg_count,
            "word_count": word_count,
            "total_online_seconds": pat.total_online_seconds,
            "last_active": pat.last_active
        })
        
    return {
        "psychologists": psych_list,
        "patients": patient_list
    }



