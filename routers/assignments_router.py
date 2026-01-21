from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, timedelta

from database import get_session
from models import (
    Assignment, AssignmentRead, AssignmentWithQuestionnaire, 
    Patient, Questionnaire, Psychologist, QuestionnaireCompletion
)
from auth import get_current_user, get_current_actor, get_current_patient, verify_patient_access
from logging_utils import log_action
from utils.assignment_utils import calculate_next_scheduled_time, check_and_update_assignment_expiry

router = APIRouter()

@router.post("", response_model=AssignmentRead)
def assign_questionnaire(
    assignment: Assignment, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(assignment.patient_id, current_user, session)
    
    # Verify patient exists
    patient = session.get(Patient, assignment.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Verify questionnaire exists
    questionnaire = session.get(Questionnaire, assignment.questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # Initial scheduling
    assignment.next_scheduled_at = calculate_next_scheduled_time(assignment)
    if assignment.frequency_type: 
        assignment.status = "active"

    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "ASSIGN_QUESTIONNAIRE", 
        details={"patient_id": assignment.patient_id, "questionnaire_id": assignment.questionnaire_id}
    )
    
    return assignment

@router.get("", response_model=List[AssignmentWithQuestionnaire])
def read_assignments(
    offset: int = 0, 
    limit: int = Query(default=100, lte=100), 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    # Filter by user's patients if not admin
    if current_user.role != "admin":
        assignments = session.exec(
            select(Assignment)
            .join(Patient)
            .where(Patient.psychologist_id == current_user.id)
            .options(selectinload(Assignment.questionnaire))
            .offset(offset).limit(limit)
        ).all()
    else:
        assignments = session.exec(
            select(Assignment)
            .options(selectinload(Assignment.questionnaire))
            .offset(offset).limit(limit)
        ).all()
    
    # Check for expired assignments
    changed = False
    for a in assignments:
        if check_and_update_assignment_expiry(a, session):
            changed = True
    if changed:
        session.commit()

    return assignments

@router.get("/patient/{access_code}", response_model=List[AssignmentWithQuestionnaire])
def get_patient_assignments(
    access_code: str, 
    session: Session = Depends(get_session), 
    current_user = Depends(get_current_actor)
):
    # Security check: ensure the token matches the requested patient code
    if not hasattr(current_user, "role"): 
        if current_user.access_code != access_code:
            raise HTTPException(status_code=403, detail="Access denied")
    
    statement = select(Patient).where(Patient.access_code == access_code).options(
        selectinload(Patient.assignments).selectinload(Assignment.questionnaire)
    )
    results = session.exec(statement)
    patient = results.first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Check for expired assignments
    changed = False
    for a in patient.assignments:
        if check_and_update_assignment_expiry(a, session):
            changed = True
    if changed:
        session.commit()
        
    return patient.assignments

@router.get("/patient-admin/{patient_id}", response_model=List[AssignmentWithQuestionnaire])
def get_patient_assignments_admin(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    """Get assignments for a patient by patient_id (for admin view)"""
    verify_patient_access(patient_id, current_user, session)
    statement = select(Assignment).where(Assignment.patient_id == patient_id).options(
        selectinload(Assignment.questionnaire)
    ).order_by(Assignment.assigned_at.desc())
    assignments = session.exec(statement).all()

    # Check for expired assignments
    changed = False
    for a in assignments:
        if check_and_update_assignment_expiry(a, session):
            changed = True
    if changed:
        session.commit()

    return assignments

@router.post("/{assignment_id}/submit", response_model=AssignmentRead)
def submit_assignment(
    assignment_id: int, 
    answers: List[dict], 
    session: Session = Depends(get_session), 
    current_user = Depends(get_current_patient)
):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Register completion
    is_delayed = False
    scheduled_at = assignment.next_scheduled_at
    if assignment.next_scheduled_at:
        if datetime.utcnow() > assignment.next_scheduled_at + timedelta(hours=2):
            is_delayed = True

    completion = QuestionnaireCompletion(
        assignment_id=assignment.id,
        patient_id=assignment.patient_id,
        questionnaire_id=assignment.questionnaire_id,
        answers=answers,
        scheduled_at=scheduled_at,
        completed_at=datetime.utcnow(),
        is_delayed=is_delayed
    )
    session.add(completion)
    
    if not assignment.frequency_type or assignment.frequency_count == 0:
        assignment.status = "completed"
        assignment.answers = answers
    else:
        assignment.next_scheduled_at = calculate_next_scheduled_time(assignment)
        if assignment.end_date:
            try:
                end_dt = datetime.fromisoformat(assignment.end_date)
                if datetime.utcnow() > end_dt:
                    assignment.status = "completed"
            except:
                pass
    
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment

@router.get("/completions/{patient_id}", response_model=List[QuestionnaireCompletion])
def get_questionnaire_completions(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(patient_id, current_user, session)
    statement = select(QuestionnaireCompletion).where(QuestionnaireCompletion.patient_id == patient_id).options(
        selectinload(QuestionnaireCompletion.questionnaire)
    ).order_by(QuestionnaireCompletion.completed_at.desc())
    results = session.exec(statement).all()
    return results

@router.patch("/{assignment_id}", response_model=AssignmentRead)
def update_assignment_status(
    assignment_id: int, 
    status_update: dict, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    verify_patient_access(assignment.patient_id, current_user, session)
    
    if "status" in status_update:
        assignment.status = status_update["status"]
    
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "UPDATE_ASSIGNMENT_STATUS", 
        details={"assignment_id": assignment_id, "status": assignment.status}
    )
    
    return assignment

@router.delete("/{assignment_id}")
def delete_assignment(assignment_id: int, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    session.delete(assignment)
    session.commit()
    
    log_action(session, 0, "system", "Unknown", "DELETE_ASSIGNMENT", details={"assignment_id": assignment_id})
    
    return {"ok": True}