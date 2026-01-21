from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import Questionnaire, QuestionnaireRead, Psychologist
from auth import get_current_user
from logging_utils import log_action

router = APIRouter()

@router.post("", response_model=QuestionnaireRead)
def create_questionnaire(
    questionnaire: Questionnaire, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    session.add(questionnaire)
    session.commit()
    session.refresh(questionnaire)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "CREATE_QUESTIONNAIRE", details={"title": questionnaire.title})
    
    return {
        "id": questionnaire.id,
        "title": questionnaire.title,
        "icon": questionnaire.icon,
        "questions": questionnaire.questions,
        "created_at": questionnaire.created_at
    }

@router.get("", response_model=List[QuestionnaireRead])
def read_questionnaires(
    offset: int = 0, 
    limit: int = Query(default=100, lte=100), 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    questionnaires = session.exec(select(Questionnaire).offset(offset).limit(limit)).all()
    return questionnaires

@router.put("/{questionnaire_id}", response_model=QuestionnaireRead)
def update_questionnaire(
    questionnaire_id: int, 
    updated_q: Questionnaire, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    questionnaire = session.get(Questionnaire, questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    
    questionnaire.title = updated_q.title
    questionnaire.description = updated_q.description
    questionnaire.questions = updated_q.questions
    
    session.add(questionnaire)
    session.commit()
    session.refresh(questionnaire)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_QUESTIONNAIRE", details={"questionnaire_id": questionnaire_id})
    
    return questionnaire

@router.delete("/{questionnaire_id}")
def delete_questionnaire(
    questionnaire_id: int, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    questionnaire = session.get(Questionnaire, questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    session.delete(questionnaire)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_QUESTIONNAIRE", details={"questionnaire_id": questionnaire_id})
    
    return {"ok": True}