from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from sqlalchemy import func
from typing import Optional

from database import get_session
from models import Patient, Message, Assignment, QuestionnaireCompletion, Questionnaire, Psychologist, Session as TherapySession
from auth import get_current_user
from utils.assignment_utils import check_and_update_assignment_expiry
from utils.logger import logger

router = APIRouter()

@router.get("/stats")
def get_dashboard_stats(
    psychologist_id: Optional[int] = None, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    # Non-admin users can only see their own stats
    if current_user.role != "admin":
        psychologist_id = current_user.id
    
    # Base queries - Filtering deleted_at == None
    q_patients = select(Patient).where(Patient.deleted_at == None)
    q_messages = select(Message).where(Message.deleted_at == None)
    q_recent_msgs = select(Message).where(Message.deleted_at == None).order_by(Message.created_at.desc()).limit(5)
    q_recent_assigns = select(Assignment).where(Assignment.deleted_at == None).order_by(Assignment.assigned_at.desc()).limit(5)
    
    if psychologist_id:
        q_patients = q_patients.where(Patient.psychologist_id == psychologist_id)
        q_messages = select(Message).join(Patient).where(Patient.psychologist_id == psychologist_id, Message.deleted_at == None)
        q_recent_msgs = select(Message).join(Patient).where(
            Patient.psychologist_id == psychologist_id,
            Message.deleted_at == None
        ).order_by(Message.created_at.desc()).limit(5)
        q_recent_assigns = select(Assignment).join(Patient).where(
            Patient.psychologist_id == psychologist_id,
            Assignment.deleted_at == None
        ).order_by(Assignment.assigned_at.desc()).limit(5)
    
    total_patients = session.exec(q_patients).all()
    total_messages = session.exec(q_messages).all()
    recent_messages = session.exec(q_recent_msgs).all()
    recent_assignments = session.exec(q_recent_assigns).all()
    
    activity_log = []
    
    for msg in recent_messages:
        if not msg.is_from_patient:
            continue
        p = session.get(Patient, msg.patient_id)
        if p and p.deleted_at: p = None # Ignore deleted patient snapshot
        p_name = p.patient_code if p else "Unknown"
        activity_log.append({
            "type": "message",
            "patient": p_name,
            "patient_id": p.id if p else None,
            "action": "Nuevo mensaje recibido",
            "time": msg.created_at,
            "timestamp": msg.created_at.timestamp()
        })
        
    for assign in recent_assignments:
        p = session.get(Patient, assign.patient_id)
        if p and p.deleted_at: p = None
        p_name = p.patient_code if p else "Unknown"
        q_title = "Cuestionario"
        if assign.questionnaire_id:
            q = session.get(Questionnaire, assign.questionnaire_id)
            if q and q.deleted_at: q = None
            if q: q_title = q.title
        
        action = f"Asignada {q_title}"
        if assign.status == "completed":
            action = f"Completada {q_title}"
            
        activity_log.append({
            "type": "assignment",
            "patient": p_name,
            "patient_id": p.id if p else None,
            "action": action,
            "time": assign.assigned_at,
            "timestamp": assign.assigned_at.timestamp()
        })
    
    # Sort by timestamp desc and take top 10
    activity_log.sort(key=lambda x: x["timestamp"], reverse=True)
    final_activity = activity_log[:10]
    
    q_completed_questionnaires = select(func.count(QuestionnaireCompletion.id)).where(
        QuestionnaireCompletion.status == "completed",
        QuestionnaireCompletion.deleted_at == None
    )
    q_pending_questionnaires = select(Assignment).where(Assignment.status != "completed", Assignment.deleted_at == None)
    
    q_unread_questionnaires = select(func.count(QuestionnaireCompletion.id)).where(
        QuestionnaireCompletion.status == "completed",
        QuestionnaireCompletion.read_by_therapist == False,
        QuestionnaireCompletion.deleted_at == None
    )
    
    if psychologist_id:
        q_completed_questionnaires = select(func.count(QuestionnaireCompletion.id)).join(
            Patient, QuestionnaireCompletion.patient_id == Patient.id
        ).where(
            Patient.psychologist_id == psychologist_id,
            QuestionnaireCompletion.status == "completed",
            QuestionnaireCompletion.deleted_at == None
        )
        q_unread_questionnaires = select(func.count(QuestionnaireCompletion.id)).join(
            Patient, QuestionnaireCompletion.patient_id == Patient.id
        ).where(
            Patient.psychologist_id == psychologist_id,
            QuestionnaireCompletion.status == "completed",
            QuestionnaireCompletion.read_by_therapist == False,
            QuestionnaireCompletion.deleted_at == None
        )
        q_pending_questionnaires = q_pending_questionnaires.join(Patient).where(Patient.psychologist_id == psychologist_id)
    
    completed_questionnaires_count = session.exec(q_completed_questionnaires).one()
    unread_questionnaires_count = session.exec(q_unread_questionnaires).one()
    pending_questionnaires_list = session.exec(q_pending_questionnaires).all()
    
    # Check for expired ones in the pending list
    changed = False
    for a in pending_questionnaires_list:
        if check_and_update_assignment_expiry(a, session):
            changed = True
    if changed:
        session.commit()
    
    # Recount active
    pending_count = len([a for a in pending_questionnaires_list if a.status != "completed"])

    # Online Patients Count - Filter using the 120s window logic from the model
    q_online_base = select(Patient).where(Patient.is_online == True, Patient.deleted_at == None)
    if psychologist_id:
        q_online_base = q_online_base.where(Patient.psychologist_id == psychologist_id)
    
    online_patients_candidates = session.exec(q_online_base).all()
    # Apply the is_active_now property logic (120s check)
    online_patients = [p for p in online_patients_candidates if p.is_active_now]

    # Unread messages count (from patients to psychologist)
    q_unread_messages = select(func.count(Message.id)).join(Patient).where(
        Message.is_from_patient == True,
        Message.read == False,
        Message.deleted_at == None
    )
    if psychologist_id:
        q_unread_messages = q_unread_messages.where(Patient.psychologist_id == psychologist_id)
    
    unread_messages_count = session.exec(q_unread_messages).one()

    # Open Sessions (Number of chats with messages)
    q_open_sessions = select(func.count(func.distinct(Message.patient_id))).where(
        Message.deleted_at == None
    )
    if psychologist_id:
        q_open_sessions = q_open_sessions.join(Patient).where(Patient.psychologist_id == psychologist_id)
    
    open_sessions_count = session.exec(q_open_sessions).one()

    # UNANSWERED MESSAGES (Last message in conversation is from patient)
    # 1. Subquery to find the latest message ID for each patient
    last_msg_subq = select(
        Message.patient_id,
        func.max(Message.id).label("max_id")
    ).where(Message.deleted_at == None).group_by(Message.patient_id).subquery()

    # 2. Query to get the patients whose latest message is from them
    q_unanswered_patients = select(Patient).join(
        Message, Patient.id == Message.patient_id
    ).join(
        last_msg_subq, Message.id == last_msg_subq.c.max_id
    ).where(Message.is_from_patient == True, Patient.deleted_at == None)
    
    if psychologist_id:
        q_unanswered_patients = q_unanswered_patients.where(Patient.psychologist_id == psychologist_id)

    unanswered_patients_list = session.exec(q_unanswered_patients).all()
    unanswered_messages_count = len(unanswered_patients_list)
    unanswered_details = [{"id": p.id, "patient_code": p.patient_code} for p in unanswered_patients_list]

    # AI Statistics
    q_base_psychologist_msgs = select(Message).join(Patient).where(
        Message.is_from_patient == False,
        Message.deleted_at == None
    )
    if psychologist_id:
        q_base_psychologist_msgs = q_base_psychologist_msgs.where(Patient.psychologist_id == psychologist_id)
    
    live_msgs = session.exec(q_base_psychologist_msgs).all()
    total_sent_messages = len(live_msgs)
    
    ai_generated_count = len([m for m in live_msgs if m.used_ai_suggestion])
    ai_edited_count = len([m for m in live_msgs if m.used_ai_suggestion and m.was_edited_by_human])
    ai_original_count = ai_generated_count - ai_edited_count
    manual_count = total_sent_messages - ai_generated_count

    # --- ADDED: Include stats from Saved Sessions ---
    q_sessions = select(TherapySession).where(TherapySession.deleted_at == None)
    if psychologist_id:
        q_sessions = q_sessions.where(TherapySession.psychologist_id == psychologist_id)
    
    all_sessions = session.exec(q_sessions).all()
    for s in all_sessions:
        if not s.chat_snapshot:
            continue
        for msg in s.chat_snapshot:
            # Snapshot messages use "sender" key ("therapist" | "patient")
            if msg.get("sender") == "therapist":
                total_sent_messages += 1
                ai_log_id = msg.get("ai_suggestion_log_id")
                # In some versions it might be "was_edited_by_human"
                was_edited = msg.get("was_edited_by_human", False)
                
                if ai_log_id:
                    ai_generated_count += 1
                    if was_edited:
                        ai_edited_count += 1
                    else:
                        ai_original_count += 1
                else:
                    manual_count += 1

    return {
        "total_patients": len(total_patients),
        "total_messages": len(total_messages),
        "unread_messages": unread_messages_count,
        "completed_questionnaires": completed_questionnaires_count,
        "unread_questionnaires": unread_questionnaires_count,
        "pending_questionnaires": pending_count,
        "recent_activity": final_activity,
        "online_patients": len(online_patients),
        "open_sessions": open_sessions_count,
        "unanswered_messages": unanswered_messages_count,
        "unanswered_details": unanswered_details,
        "ai_stats": {
            "total_sent": total_sent_messages,
            "ai_generated": ai_generated_count,
            "ai_edited": ai_edited_count,
            "ai_original": ai_original_count,
            "manual": manual_count
        }
    }
