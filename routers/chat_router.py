import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from typing import List
from pydantic import BaseModel

from database import get_session
from models import Psychologist
from auth import get_current_user
from llm_service import generate_response_options, generate_response_options_stream

router = APIRouter()

class ChatContext(BaseModel):
    messages: List[dict]  # [{"role": "user", "content": "..."}, ...]
    patient_id: int

from models import AISuggestionLog


@router.post("/recommendations/stream")
async def get_chat_recommendations_stream(
    context: ChatContext,
    session: Session = Depends(get_session),
    current_user: Psychologist = Depends(get_current_user)
):
    """
    Endpoint SSE: llama a los 3 modelos en paralelo y hace streaming de cada
    opción en cuanto está disponible. El evento final 'done' incluye el
    ai_suggestion_log_id guardado en BD.
    """
    print(f"--- Stream Recommendation Request from Psychologist {current_user.id} ---")
    
    therapist = session.get(Psychologist, current_user.id)
    if not therapist:
        raise HTTPException(status_code=404, detail="Therapist not found")

    # Capturamos los parámetros ahora (antes de entrar al generador)
    therapist_style = therapist.ai_style
    therapist_tone = therapist.ai_tone
    
    # Combinamos instrucciones globales del terapeuta con las específicas del paciente
    from models import Patient
    patient = session.get(Patient, context.patient_id)
    patient_instructions = patient.ai_instructions if patient else ""
    
    therapist_instructions = therapist.ai_instructions or ""
    if patient_instructions:
        combined_instructions = f"{therapist_instructions}\n\nINSTRUCCIONES PRIORITARIAS PARA ESTE PACIENTE (DE OBLIGADO CUMPLIMIENTO):\n{patient_instructions}"
    else:
        combined_instructions = therapist_instructions
        
    psychologist_id = therapist.id
    patient_id = context.patient_id
    messages = context.messages

    async def event_generator():
        final_options = []
        try:
            async for event in generate_response_options_stream(
                messages,
                therapist_style=therapist_style,
                therapist_tone=therapist_tone,
                therapist_instructions=combined_instructions
            ):
                if event["type"] == "option":
                    yield f"data: {json.dumps(event)}\n\n"
                    await asyncio.sleep(0)  # Flush al cliente

                elif event["type"] == "done":
                    final_options = event["options"]
                    # Guardar en BD
                    try:
                        new_ai_log = AISuggestionLog(
                            patient_id=patient_id,
                            psychologist_id=psychologist_id,
                            ai_style_used=therapist_style,
                            ai_tone_used=therapist_tone,
                            ai_instructions_used=combined_instructions,
                            suggestion_model1=final_options[0] if len(final_options) > 0 else "",
                            suggestion_model2=final_options[1] if len(final_options) > 1 else "",
                            suggestion_model3=final_options[2] if len(final_options) > 2 else "",
                            raw_options=json.dumps(final_options)
                        )
                        session.add(new_ai_log)
                        session.commit()
                        session.refresh(new_ai_log)
                        log_id = new_ai_log.id
                    except Exception as db_err:
                        print(f"Error saving AISuggestionLog: {db_err}")
                        session.rollback()
                        log_id = None

                    done_event = {
                        "type": "done",
                        "ai_suggestion_log_id": log_id,
                        "options": final_options
                    }
                    yield f"data: {json.dumps(done_event)}\n\n"

        except Exception as e:
            print(f"Error in stream event_generator: {e}")
            error_event = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@router.post("/recommendations")
async def get_chat_recommendations(
    context: ChatContext,
    session: Session = Depends(get_session),
    current_user: Psychologist = Depends(get_current_user)
):
    """Endpoint estándar (no-streaming) — ahora también usa llamadas paralelas internamente."""
    print(f"--- Chat Recommendation Request from Psychologist {current_user.id} ---")
    try:
        therapist = session.get(Psychologist, current_user.id)
        if not therapist:
            raise HTTPException(status_code=404, detail="Therapist not found")

        # Fetch patient instructions
        from models import Patient
        patient = session.get(Patient, context.patient_id)
        patient_instructions = patient.ai_instructions if patient else ""
        
        therapist_instructions = therapist.ai_instructions or ""
        if patient_instructions:
            combined_instructions = f"{therapist_instructions}\n\n### INSTRUCCIONES PRIORITARIAS PARA ESTE PACIENTE (DE OBLIGADO CUMPLIMIENTO):\n{patient_instructions}\n\nIMPORTANTE: Estas instrucciones específicas para este paciente concreto son las más importantes y deben prevalecer sobre cualquier otra instrucción general en caso de conflicto."
        else:
            combined_instructions = therapist_instructions

        result = await generate_response_options(
            context.messages,
            therapist_style=therapist.ai_style,
            therapist_tone=therapist.ai_tone,
            therapist_instructions=combined_instructions
        )
        new_ai_log = AISuggestionLog(
            patient_id=context.patient_id,
            psychologist_id=therapist.id,
            ai_style_used=therapist.ai_style,
            ai_tone_used=therapist.ai_tone,
            ai_instructions_used=combined_instructions,
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