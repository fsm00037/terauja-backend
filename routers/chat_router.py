from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List
from pydantic import BaseModel

from database import get_session
from models import Psychologist
from auth import get_current_user
from llm_service import generate_response_options

router = APIRouter()

class ChatContext(BaseModel):
    messages: List[dict] # [{"role": "user", "content": "..."}, ...]
    patient_id: int

from models import AISuggestionLog # Asegúrate de importar tu nuevo modelo

@router.post("/recommendations")
def get_chat_recommendations(
    context: ChatContext, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    print(f"--- Chat Recommendation Request from Psychologist {current_user.id} ---")
    try:
        therapist = session.get(Psychologist, current_user.id)
        if not therapist:
            raise HTTPException(status_code=404, detail="Therapist not found")

        result = generate_response_options(
            context.messages,
            therapist_style=therapist.ai_style,
            therapist_tone=therapist.ai_tone,
            therapist_instructions=therapist.ai_instructions
        )
        new_ai_log = AISuggestionLog(
            patient_id=context.patient_id,
            psychologist_id=therapist.id,
            ai_style_used=therapist.ai_style,
            ai_tone_used=therapist.ai_tone,
            ai_instructions_used=therapist.ai_instructions,
            suggestion_model1=result["options"][0] or "",
            suggestion_model2=result["options"][1] or "",
            suggestion_model3=result["options"][2] or "",
            raw_options=result["raw_options"]
        )
        
        session.add(new_ai_log)
        session.commit()
        session.refresh(new_ai_log)

        return {
            "recommendations": result["options"],
            "ai_suggestion_log_id": new_ai_log.id
        }

    except Exception as e:
        print(f"Error getting recommendations: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")