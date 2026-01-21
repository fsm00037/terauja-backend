from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime

from database import get_session
from models import AssessmentStat, AssessmentStatRead, Psychologist
from auth import get_current_user, verify_patient_access
from logging_utils import log_action

router = APIRouter()

@router.get("/{patient_id}", response_model=List[AssessmentStatRead])
def get_assessment_stats(
    patient_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(patient_id, current_user, session)
    statement = select(AssessmentStat).where(
        AssessmentStat.patient_id == patient_id
    ).order_by(AssessmentStat.created_at.desc())
    return session.exec(statement).all()

@router.post("", response_model=AssessmentStatRead)
def create_assessment_stat(
    stat: AssessmentStat, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    verify_patient_access(stat.patient_id, current_user, session)
    session.add(stat)
    session.commit()
    session.refresh(stat)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "CREATE_STAT", 
        details={"patient_id": stat.patient_id, "label": stat.label}
    )
    
    return stat

@router.put("/{stat_id}", response_model=AssessmentStatRead)
def update_assessment_stat(
    stat_id: int, 
    stat_update: AssessmentStat, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    stat = session.get(AssessmentStat, stat_id)
    if not stat:
        raise HTTPException(status_code=404, detail="Assessment stat not found")
    
    verify_patient_access(stat.patient_id, current_user, session)
    
    stat.label = stat_update.label
    stat.value = stat_update.value
    stat.status = stat_update.status
    stat.color = stat_update.color
    stat.updated_at = datetime.utcnow()
    
    session.add(stat)
    session.commit()
    session.refresh(stat)
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "UPDATE_STAT", 
        details={"stat_id": stat_id}
    )
    
    return stat

@router.delete("/{stat_id}")
def delete_assessment_stat(
    stat_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    stat = session.get(AssessmentStat, stat_id)
    if not stat:
        raise HTTPException(status_code=404, detail="Assessment stat not found")
    verify_patient_access(stat.patient_id, current_user, session)
    session.delete(stat)
    session.commit()
    
    log_action(
        session, current_user.id, "psychologist", current_user.name, 
        "DELETE_STAT", 
        details={"stat_id": stat_id}
    )
    
    return {"ok": True}