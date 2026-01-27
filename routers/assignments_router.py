from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, or_, SQLModel
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, timedelta

from database import get_session
from models import (
    Assignment, AssignmentRead, AssignmentWithQuestionnaire, 
    Patient, Questionnaire, Psychologist, QuestionnaireCompletion, QuestionnaireRead
)
from auth import get_current_user, get_current_actor, get_current_patient, verify_patient_access
from logging_utils import log_action
from utils.assignment_utils import calculate_next_scheduled_time, check_and_update_assignment_expiry

class QuestionnaireCompletionWithDetails(SQLModel):
    id: int
    assignment_id: int
    patient_id: int
    questionnaire_id: int
    answers: List[dict] | None = None
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    is_delayed: bool
    deadline_hours: int | None = None
    questionnaire: QuestionnaireRead | None = None


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
    # assignment.next_scheduled_at = calculate_next_scheduled_time(assignment) # REMOVED RANDOM LOGIC
    if assignment.frequency_type: 
        assignment.status = "active"

    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    
    # Generate scheduled completions
    from utils.assignment_utils import generate_schedule_dates
    if assignment.start_date and assignment.end_date:
        dates = generate_schedule_dates(
            assignment.start_date, 
            assignment.end_date, 
            assignment.frequency_type, 
            assignment.frequency_count or 1,
            assignment.window_start or "09:00",
            assignment.window_end or "21:00"
        )
        
        for i, dt in enumerate(dates):
            completion = QuestionnaireCompletion(
                assignment_id=assignment.id,
                patient_id=assignment.patient_id,
                questionnaire_id=assignment.questionnaire_id,
                scheduled_at=dt,
                status="pending"
            )
            session.add(completion)
            
            # Set next_scheduled_at to the first one
            if i == 0:
                assignment.next_scheduled_at = dt
        
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
    base_query = select(Assignment).where(Assignment.deleted_at == None)
    if current_user.role != "admin":
        assignments = session.exec(
            base_query
            .join(Patient)
            .where(Patient.psychologist_id == current_user.id)
            .options(selectinload(Assignment.questionnaire))
            .offset(offset).limit(limit)
        ).all()
    else:
        assignments = session.exec(
            base_query
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
    if not patient or patient.deleted_at:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Filter deleted assignments
    active_assignments = [a for a in patient.assignments if a.deleted_at is None]
    
    # Check for expired assignments
    changed = False
    for a in active_assignments:
        if check_and_update_assignment_expiry(a, session):
            changed = True
    if changed:
        session.commit()
        
    return active_assignments

@router.get("/patient-admin/{patient_id}", response_model=List[AssignmentWithQuestionnaire])
def get_patient_assignments_admin(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    """Get assignments for a patient by patient_id (for admin view)"""
    verify_patient_access(patient_id, current_user, session)
    statement = select(Assignment).where(Assignment.patient_id == patient_id, Assignment.deleted_at == None).options(
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
    if not assignment or assignment.deleted_at:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Register completion
    is_delayed = False
    
    # 1. Find the earliest pending completion for this assignment
    statement = (
        select(QuestionnaireCompletion)
        .where(QuestionnaireCompletion.assignment_id == assignment_id)
        .where(or_(QuestionnaireCompletion.status == "pending", QuestionnaireCompletion.status == "sent", QuestionnaireCompletion.status == "missed"))
        .where(QuestionnaireCompletion.deleted_at == None)
        .order_by(QuestionnaireCompletion.scheduled_at)
    )
    pending_completion = session.exec(statement).first()

    if pending_completion:
        # Update existing pending completion
        completion = pending_completion
        completion.answers = answers
        completion.completed_at = datetime.utcnow()
        completion.status = "completed"
        
        # Check delay
        if completion.scheduled_at:
             deadline = assignment.deadline_hours or 24
             if datetime.utcnow() > completion.scheduled_at + timedelta(hours=deadline):
                 completion.is_delayed = True
    else:
        # Fallback: create new one (shouldn't happen with new logic but safe fallback)
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
            is_delayed=is_delayed,
            status="completed"
        )
        session.add(completion)
    
    # Update Assignment Status and Next Schedule
    
    # Find NEXT pending to update assignment.next_scheduled_at
    next_pending = session.exec(
        select(QuestionnaireCompletion)
        .where(QuestionnaireCompletion.assignment_id == assignment_id)
        .where(or_(QuestionnaireCompletion.status == "pending", QuestionnaireCompletion.status == "sent", QuestionnaireCompletion.status == "missed"))
        .where(QuestionnaireCompletion.deleted_at == None)
        .order_by(QuestionnaireCompletion.scheduled_at)
    ).first()
    
    if next_pending:
        assignment.next_scheduled_at = next_pending.scheduled_at
    else:
        # No more pending items
        assignment.next_scheduled_at = None
        assignment.status = "completed"
    
    session.add(assignment)
    session.add(completion)
    session.commit()
    session.refresh(assignment)
    return assignment

@router.get("/completions/{patient_id}", response_model=List[QuestionnaireCompletionWithDetails])
def get_questionnaire_completions(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    """Get questionnaire completions for a patient by patient_id"""
    verify_patient_access(patient_id, current_user, session)
    
    # Check for missed completions
    # Logic: if pending and scheduled_at + 24h < now -> missed
    pending_statement = (
        select(QuestionnaireCompletion)
        .where(QuestionnaireCompletion.patient_id == patient_id)
        .where(QuestionnaireCompletion.status == "pending")
        .where(QuestionnaireCompletion.deleted_at == None)
    )
    pending_completions = session.exec(pending_statement).all()
    
    changed = False
    now = datetime.utcnow()
    for c in pending_completions:
        if c.scheduled_at and (c.scheduled_at + timedelta(hours=24) < now):
             c.status = "missed"
             session.add(c)
             changed = True
    
    if changed:
        session.commit()

    statement = (
        select(QuestionnaireCompletion)
        .where(QuestionnaireCompletion.patient_id == patient_id, QuestionnaireCompletion.deleted_at == None)
        .options(selectinload(QuestionnaireCompletion.questionnaire))
        .order_by(QuestionnaireCompletion.scheduled_at.desc())
    )
    completions = session.exec(statement).all()
    return completions

@router.get("/my-pending", response_model=List[QuestionnaireCompletionWithDetails])
def get_my_pending_assignments(
    session: Session = Depends(get_session),
    current_user: Patient = Depends(get_current_patient)
):
    """
    Get pending assignments for the current patient.
    Checks for any pending completions that are due (scheduled_at <= now).
    Marks them as 'sent' if they are not already sent.
    Returns all 'sent' (and previously 'sent') items that are not completed or missed.
    """
    now = datetime.now()
    
    # 1. Update pending -> sent if due
    statement = (
        select(QuestionnaireCompletion)
        .where(QuestionnaireCompletion.patient_id == current_user.id)
        .where(QuestionnaireCompletion.status == "pending")
        .where(QuestionnaireCompletion.scheduled_at <= now)
        .where(QuestionnaireCompletion.deleted_at == None)
    )
    due_completions = session.exec(statement).all()
    
    for c in due_completions:
        c.status = "sent"
        session.add(c)
    
    if due_completions:
        session.commit()
    
    # 1.5 Update sent -> missed if > deadline
    statement_missed = (
        select(QuestionnaireCompletion)
        .where(QuestionnaireCompletion.patient_id == current_user.id)
        .where(QuestionnaireCompletion.status == "sent")
        .where(QuestionnaireCompletion.deleted_at == None)
        .options(selectinload(QuestionnaireCompletion.assignment))
    )
    potential_missed = session.exec(statement_missed).all()
    missed_changed = False
    for c in potential_missed:
        deadline_hours = c.assignment.deadline_hours or 24
        if c.scheduled_at and (c.scheduled_at + timedelta(hours=deadline_hours) < now):
             c.status = "missed"
             session.add(c)
             missed_changed = True
    
    if missed_changed:
        session.commit()
        
    # 2. Fetch all 'sent' or 'missed' items
    statement_sent = (
        select(QuestionnaireCompletion)
        .where(QuestionnaireCompletion.patient_id == current_user.id)
        .where(or_(QuestionnaireCompletion.status == "sent", QuestionnaireCompletion.status == "missed")) 
        .where(QuestionnaireCompletion.deleted_at == None)
        .options(selectinload(QuestionnaireCompletion.questionnaire))
        .options(selectinload(QuestionnaireCompletion.assignment))
        .order_by(QuestionnaireCompletion.scheduled_at)
    )
    # Re-querying to get the updated status and questionnaire relation
    sent_completions = session.exec(statement_sent).all()
    
    # Enrich with deadline_hours
    results = []
    for c in sent_completions:
        # Create response object from model
        c_dict = c.model_dump()
        c_dict['deadline_hours'] = c.assignment.deadline_hours
        c_dict['questionnaire'] = c.questionnaire 
        results.append(QuestionnaireCompletionWithDetails(**c_dict))

    return results


@router.patch("/{assignment_id}", response_model=AssignmentRead)
def update_assignment_status(
    assignment_id: int, 
    status_update: dict, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    assignment = session.get(Assignment, assignment_id)
    if not assignment or assignment.deleted_at:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    verify_patient_access(assignment.patient_id, current_user, session)
    
    if "status" in status_update:
        new_status = status_update["status"]
        
        # Logic for early completion/finalization
        if new_status == "completed" and assignment.status != "completed":
            from datetime import datetime
            now = datetime.utcnow()
            
            # Soft delete future pending completions
            future_pending = session.exec(
                select(QuestionnaireCompletion)
                .where(QuestionnaireCompletion.assignment_id == assignment_id)
                .where(QuestionnaireCompletion.status == "pending")
                .where(QuestionnaireCompletion.scheduled_at > now)
                .where(QuestionnaireCompletion.deleted_at == None)
            ).all()
            
            for fp in future_pending:
                fp.deleted_at = datetime.now(timezone.utc)
                session.add(fp)
                
            # Update end date to now to reflect early finish
            # assignment.end_date = now.strftime("%Y-%m-%d") # Optional: depends on business rule? User said "up to date"
            
        assignment.status = new_status
    
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
def delete_assignment(assignment_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    from datetime import datetime, timezone
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    verify_patient_access(assignment.patient_id, current_user, session)
    
    # Cascade soft delete completions
    completions = session.exec(select(QuestionnaireCompletion).where(QuestionnaireCompletion.assignment_id == assignment_id, QuestionnaireCompletion.deleted_at == None)).all()
    now = datetime.now(timezone.utc)
    for completion in completions:
        completion.deleted_at = now
        session.add(completion)
        
    assignment.deleted_at = now
    session.add(assignment)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_ASSIGNMENT", details={"assignment_id": assignment_id})
    
    return {"ok": True}

@router.patch("/completions/{completion_id}", response_model=QuestionnaireCompletion)
def update_completion(
    completion_id: int, 
    update_data: dict, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    completion = session.get(QuestionnaireCompletion, completion_id)
    if not completion or completion.deleted_at:
        raise HTTPException(status_code=404, detail="Completion not found")
        
    verify_patient_access(completion.patient_id, current_user, session)
    
    if "scheduled_at" in update_data:
        try:
            # Handle ISO string from frontend
            dt = datetime.fromisoformat(update_data["scheduled_at"].replace("Z", ""))
            completion.scheduled_at = dt
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
            
    if "status" in update_data:
        completion.status = update_data["status"]
        
    session.add(completion)
    session.commit()
    session.refresh(completion)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "UPDATE_COMPLETION", 
        details={"completion_id": completion_id, "update": update_data}
    )
    
    return completion

@router.patch("/completions/{completion_id}/read")
def mark_completion_as_read(
    completion_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    completion = session.get(QuestionnaireCompletion, completion_id)
    if not completion or completion.deleted_at:
        raise HTTPException(status_code=404, detail="Completion not found")
        
    verify_patient_access(completion.patient_id, current_user, session)
    
    completion.read_by_therapist = True
    session.add(completion)
    session.commit()
    
    return {"ok": True}
