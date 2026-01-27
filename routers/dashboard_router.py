from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from sqlalchemy import func
from typing import Optional

from database import get_session
from models import Patient, Message, Assignment, QuestionnaireCompletion, Questionnaire, Psychologist
from auth import get_current_user
from utils.assignment_utils import check_and_update_assignment_expiry

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
        p = session.get(Patient, msg.patient_id)
        if p and p.deleted_at: p = None # Ignore deleted patient snapshot
        p_name = p.patient_code if p else "Unknown"
        activity_log.append({
            "type": "message",
            "patient": p_name,
            "patient_id": p.id if p else None,
            "action": "Nuevo mensaje recibido" if msg.is_from_patient else "Nuevo mensaje enviado",
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

    # Online Patients Count
    q_online = select(Patient).where(Patient.is_online == True, Patient.deleted_at == None)
    if psychologist_id:
        q_online = q_online.where(Patient.psychologist_id == psychologist_id)
    online_patients = session.exec(q_online).all()

    return {
        "total_patients": len(total_patients),
        "total_messages": len(total_messages),
        "completed_questionnaires": completed_questionnaires_count,
        "unread_questionnaires": unread_questionnaires_count,
        "pending_questionnaires": pending_count,
        "recent_activity": final_activity,
        "online_patients": len(online_patients)
    }
