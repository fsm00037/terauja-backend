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

@router.post("/recommendations")
def get_chat_recommendations(
    context: ChatContext, 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(get_current_user)
):
    print(f"--- Chat Recommendation Request from Psychologist {current_user.id} ---")
    try:
        # Retrieve therapist's AI configuration
        therapist = session.get(Psychologist, current_user.id)
        if not therapist:
            raise HTTPException(status_code=404, detail="Therapist not found")

        # Agrega estos prints para debuggear
        print(f"DEBUG - Therapist ID: {current_user.id}")
        print(f"DEBUG - Style: {therapist.ai_style}")
        print(f"DEBUG - Tone: {therapist.ai_tone}")

        # Generate recommendations with therapist-specific configuration
        recommendations = generate_response_options(
            context.messages,
            therapist_style=therapist.ai_style,
            therapist_tone=therapist.ai_tone,
            therapist_instructions=therapist.ai_instructions
        )
        return {"recommendations": recommendations}
    except Exception as e:
        print(f"Error getting recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")