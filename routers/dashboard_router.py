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
    
    # Base queries
    q_patients = select(Patient)
    q_messages = select(Message)
    q_recent_msgs = select(Message).order_by(Message.created_at.desc()).limit(5)
    q_recent_assigns = select(Assignment).order_by(Assignment.assigned_at.desc()).limit(5)
    
    if psychologist_id:
        q_patients = q_patients.where(Patient.psychologist_id == psychologist_id)
        q_messages = select(Message).join(Patient).where(Patient.psychologist_id == psychologist_id)
        q_recent_msgs = select(Message).join(Patient).where(
            Patient.psychologist_id == psychologist_id
        ).order_by(Message.created_at.desc()).limit(5)
        q_recent_assigns = select(Assignment).join(Patient).where(
            Patient.psychologist_id == psychologist_id
        ).order_by(Assignment.assigned_at.desc()).limit(5)
    
    total_patients = session.exec(q_patients).all()
    total_messages = session.exec(q_messages).all()
    recent_messages = session.exec(q_recent_msgs).all()
    recent_assignments = session.exec(q_recent_assigns).all()
    
    activity_log = []
    
    for msg in recent_messages:
        p = session.get(Patient, msg.patient_id)
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
        p_name = p.patient_code if p else "Unknown"
        q_title = "Cuestionario"
        if assign.questionnaire_id:
            q = session.get(Questionnaire, assign.questionnaire_id)
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
    
    q_completed_questionaries = select(func.count(QuestionnaireCompletion.id))
    q_pending_questionaries = select(Assignment).where(Assignment.status != "completed")
    
    if psychologist_id:
        q_completed_questionaries = select(func.count(QuestionnaireCompletion.id)).join(
            Patient, QuestionnaireCompletion.patient_id == Patient.id
        ).where(Patient.psychologist_id == psychologist_id)
        q_pending_questionaries = q_pending_questionaries.join(Patient).where(Patient.psychologist_id == psychologist_id)

    completed_questionaries_count = session.exec(q_completed_questionaries).one()
    pending_questionaries_list = session.exec(q_pending_questionaries).all()
    
    # Check for expired ones in the pending list
    changed = False
    for a in pending_questionaries_list:
        if check_and_update_assignment_expiry(a, session):
            changed = True
    if changed:
        session.commit()
    
    # Recount active
    pending_count = len([a for a in pending_questionaries_list if a.status != "completed"])

    # Online Patients Count
    q_online = select(Patient).where(Patient.is_online == True)
    if psychologist_id:
        q_online = q_online.where(Patient.psychologist_id == psychologist_id)
    online_patients = session.exec(q_online).all()

    return {
        "total_patients": len(total_patients),
        "total_messages": len(total_messages),
        "completed_questionaries": completed_questionaries_count,
        "pending_questionaries": pending_count,
        "recent_activity": final_activity,
        "online_patients": len(online_patients)
    }