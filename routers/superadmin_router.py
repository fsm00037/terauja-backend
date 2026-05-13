from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func, SQLModel
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from database import get_session
from models import Psychologist, Patient, PsychologistRead
from auth import require_superadmin, hash_password
from utils.logger import logger

router = APIRouter()

@router.get("/stats", dependencies=[Depends(require_superadmin)])
async def get_platform_stats(session: Session = Depends(get_session)):
    """Get platform statistics for superadmin dashboard."""
    import json as json_module
    from models import Message, Session as TherapySession, AISuggestionLog
    
    total_psychologists = session.exec(select(func.count(Psychologist.id)).where(Psychologist.role != "superadmin")).one()
    total_patients = session.exec(select(func.count(Patient.id))).one()
    
    # Message stats
    messages = session.exec(select(Message)).all()
    total_messages_psychologist = sum(1 for m in messages if not m.is_from_patient)
    total_messages_patient = sum(1 for m in messages if m.is_from_patient)
    total_words = sum(len(m.content.split()) for m in messages if m.content)

    # Track which suggestion logs were edited
    edited_log_ids = set()
    
    for m in messages:
        if m.ai_suggestion_log_id and m.was_edited_by_human:
            edited_log_ids.add(m.ai_suggestion_log_id)

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
                    
                log_id = msg.get("ai_suggestion_log_id")
                if log_id and msg.get("was_edited_by_human"):
                    edited_log_ids.add(log_id)

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
    
    # Global AI Analytics
    logs = session.exec(select(AISuggestionLog)).all()
    clicked_ai = 0
    not_clicked_ai = 0
    edited_ai = 0
    
    global_model_usage = {}
    global_model_unedited = {}
    
    # Model-specific tracking
    model_stats = {} # key: model_name, value: {generations, clicked, edited}
    
    for log in logs:
        # Extract models offered
        models_list = []
        if log.models_used:
            try:
                models_list = json_module.loads(log.models_used)
            except:
                models_list = []
                
        # Register generation counts for each unique offered model
        unique_offered_models = set(models_list)
        for m_name in unique_offered_models:
            if m_name not in model_stats:
                model_stats[m_name] = {"generations": 0, "clicked": 0, "edited": 0}
            model_stats[m_name]["generations"] += 1

        if log.final_option_id is not None:
            clicked_ai += 1
            is_edited = log.id in edited_log_ids
            if is_edited:
                edited_ai += 1
            
            chosen_idx = log.final_option_id - 1
            if 0 <= chosen_idx < len(models_list):
                model_name = models_list[chosen_idx]
                global_model_usage[model_name] = global_model_usage.get(model_name, 0) + 1
                if not is_edited:
                    global_model_unedited[model_name] = global_model_unedited.get(model_name, 0) + 1
                
                # Model-specific clicked/edited increment
                if model_name not in model_stats:
                    model_stats[model_name] = {"generations": 0, "clicked": 0, "edited": 0}
                model_stats[model_name]["clicked"] += 1
                if is_edited:
                    model_stats[model_name]["edited"] += 1
        else:
            not_clicked_ai += 1
            
    # Sort rankings
    model_ranking = sorted(global_model_usage.items(), key=lambda x: x[1], reverse=True)
    model_unedited_ranking = sorted(global_model_unedited.items(), key=lambda x: x[1], reverse=True)
    
    by_model_list = []
    for m_name, s in model_stats.items():
        by_model_list.append({
            "model": m_name,
            "generations": s["generations"],
            "clicked": s["clicked"],
            "not_clicked": s["generations"] - s["clicked"],
            "edited": s["edited"]
        })
    
    return {
        "total_psychologists": total_psychologists,
        "total_patients": total_patients,
        "online_psychologists": psychologists_online,
        "online_patients": patients_online,
        "total_messages_psychologist": total_messages_psychologist,
        "total_messages_patient": total_messages_patient,
        "total_words": total_words,
        "ai_stats": {
            "total_generations": len(logs),
            "clicked_ai": clicked_ai,
            "not_clicked_ai": not_clicked_ai,
            "edited_ai": edited_ai,
            "model_ranking": [{"model": m, "count": c} for m, c in model_ranking],
            "model_unedited_ranking": [{"model": m, "count": c} for m, c in model_unedited_ranking],
            "by_model": by_model_list
        }
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

@router.get("/analysis/sessions", dependencies=[Depends(require_superadmin)])
async def get_sessions_for_analysis(session: Session = Depends(get_session)):
    """List all therapy sessions for AI usage analysis."""
    from models import Session as TherapySession, Patient, Psychologist
    
    # Query sessions joined with patient and psychologist
    statement = (
        select(TherapySession, Patient.patient_code, Psychologist.name)
        .outerjoin(Patient, TherapySession.patient_id == Patient.id)
        .outerjoin(Psychologist, TherapySession.psychologist_id == Psychologist.id)
        .where(TherapySession.deleted_at == None)
        .order_by(TherapySession.date.desc())
    )
    
    results = session.exec(statement).all()
    
    session_list = []
    for therapy_session, patient_code, psych_name in results:
        session_list.append({
            "id": therapy_session.id,
            "patient_id": therapy_session.patient_id,
            "patient_code": patient_code or f"P#{therapy_session.patient_id}",
            "psychologist_id": therapy_session.psychologist_id,
            "psychologist_name": psych_name or "Sin psicólogo",
            "date": therapy_session.date,
            "duration": therapy_session.duration,
            "description": therapy_session.description,
            "ai_summary": therapy_session.ai_summary
        })
        
    return session_list

@router.get("/analysis/sessions/{session_id}", dependencies=[Depends(require_superadmin)])
async def get_session_analysis_detail(session_id: int, session: Session = Depends(get_session)):
    """Get detailed AI analysis for a specific session."""
    import json as json_module
    from models import Session as TherapySession, Patient, Psychologist, AISuggestionLog
    
    db_session = session.get(TherapySession, session_id)
    if not db_session or db_session.deleted_at:
        raise HTTPException(status_code=404, detail="Session not found")
        
    patient = session.get(Patient, db_session.patient_id)
    psychologist = session.get(Psychologist, db_session.psychologist_id) if db_session.psychologist_id else None
    
    patient_code = patient.patient_code if patient else f"P#{db_session.patient_id}"
    psychologist_name = psychologist.name if psychologist else "Sin psicólogo"
    
    chat_snapshot = db_session.chat_snapshot or []
    enriched_messages = []
    
    # Track statistics
    total_therapist_messages = 0
    clicked_ai = 0
    not_clicked_ai = 0
    edited_ai = 0
    
    # Model usage tracking
    # model_usage_counts: { "model_name": count_of_times_chosen }
    model_usage_counts = {}
    # model_unedited_counts: { "model_name": count_of_times_chosen_without_editing }
    model_unedited_counts = {}
    
    # For each message in snapshot, enrich with AI Suggestion Log if present
    for msg in chat_snapshot:
        sender = msg.get("sender")
        text = msg.get("text", "")
        timestamp = msg.get("timestamp", "")
        was_edited = msg.get("was_edited_by_human", False)
        ai_suggestion_log_id = msg.get("ai_suggestion_log_id")
        
        enriched_msg = {
            "text": text,
            "sender": sender,
            "timestamp": timestamp,
            "was_edited_by_human": was_edited,
            "ai_suggestion_log_id": ai_suggestion_log_id,
            "ai_suggestions": None
        }
        
        if sender == "therapist":
            total_therapist_messages += 1
            
            if ai_suggestion_log_id:
                # Fetch AISuggestionLog
                log_record = session.get(AISuggestionLog, ai_suggestion_log_id)
                if log_record:
                    # Parse models_used JSON
                    models_list = []
                    if log_record.models_used:
                        try:
                            models_list = json_module.loads(log_record.models_used)
                        except:
                            models_list = []
                    
                    # Parse suggested_strategies JSON
                    strategies_list = None
                    if log_record.suggested_strategies:
                        try:
                            strategies_list = json_module.loads(log_record.suggested_strategies)
                        except:
                            strategies_list = log_record.suggested_strategies
                    
                    enriched_msg["ai_suggestions"] = {
                        "suggestion_model1": log_record.suggestion_model1,
                        "suggestion_model2": log_record.suggestion_model2,
                        "suggestion_model3": log_record.suggestion_model3,
                        "final_option_id": log_record.final_option_id,
                        "selected_strategy": log_record.selected_strategy,
                        "suggested_strategies": strategies_list,
                        "models_used": models_list,
                        "ai_style_used": log_record.ai_style_used,
                        "ai_tone_used": log_record.ai_tone_used,
                        "ai_instructions_used": log_record.ai_instructions_used,
                    }
                    
                    # Determine if therapist clicked
                    if log_record.final_option_id is not None:
                        clicked_ai += 1
                        if was_edited:
                            edited_ai += 1
                        
                        # Track model usage
                        chosen_idx = log_record.final_option_id - 1  # 0-indexed
                        if 0 <= chosen_idx < len(models_list):
                            model_name = models_list[chosen_idx]
                            model_usage_counts[model_name] = model_usage_counts.get(model_name, 0) + 1
                            if not was_edited:
                                model_unedited_counts[model_name] = model_unedited_counts.get(model_name, 0) + 1
                    else:
                        not_clicked_ai += 1
                else:
                    # Log record was not found
                    not_clicked_ai += 1
            else:
                # No suggestion log ID means they definitely did not use AI suggestions
                not_clicked_ai += 1
                
        enriched_messages.append(enriched_msg)
    
    # Build model stats
    model_ranking = sorted(model_usage_counts.items(), key=lambda x: x[1], reverse=True)
    model_unedited_ranking = sorted(model_unedited_counts.items(), key=lambda x: x[1], reverse=True)
        
    return {
        "id": db_session.id,
        "patient_id": db_session.patient_id,
        "patient_code": patient_code,
        "psychologist_id": db_session.psychologist_id,
        "psychologist_name": psychologist_name,
        "date": db_session.date,
        "duration": db_session.duration,
        "description": db_session.description,
        "notes": db_session.notes,
        "ai_summary": db_session.ai_summary,
        "chat_snapshot_enriched": enriched_messages,
        "stats": {
            "total_therapist_messages": total_therapist_messages,
            "clicked_ai": clicked_ai,
            "not_clicked_ai": not_clicked_ai,
            "edited_ai": edited_ai,
            "model_ranking": [{"model": m, "count": c} for m, c in model_ranking],
            "model_unedited_ranking": [{"model": m, "count": c} for m, c in model_unedited_ranking],
        }
    }




