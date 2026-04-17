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
from llm_service import generate_response_options, generate_response_options_stream, generate_strategy_options
from utils.logger import logger

router = APIRouter()

class ChatContext(BaseModel):
    messages: List[dict]  # [{"role": "user", "content": "..."}, ...]
    patient_id: int
    temporary_instructions: str = ""

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
    logger.info(f"Stream Recommendation: Psych {current_user.id} -> Patient {context.patient_id}")
    
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
        
    if context.temporary_instructions:
        combined_instructions += f"\n\n=== INSTRUCCIONES ESPECÍFICAS PARA ESTE TURNO (PRIORIDAD MÁXIMA) ===\n{context.temporary_instructions}"
        
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
                        logger.error(f"Error saving AISuggestionLog: {db_err}")
                        session.rollback()
                        log_id = None

                    done_event = {
                        "type": "done",
                        "ai_suggestion_log_id": log_id,
                        "options": final_options
                    }
                    yield f"data: {json.dumps(done_event)}\n\n"

        except Exception as e:
            logger.error(f"Error in stream event_generator: {e}")
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
    logger.info(f"Chat Recommendation: Psych {current_user.id} -> Patient {context.patient_id}")
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

        if context.temporary_instructions:
            combined_instructions += f"\n\n=== INSTRUCCIONES ESPECÍFICAS PARA ESTE TURNO (PRIORIDAD MÁXIMA) ===\n{context.temporary_instructions}"

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
        logger.error(f"Error getting recommendations: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")

@router.post("/strategies")
async def get_chat_strategies(
    context: ChatContext,
    current_user: Psychologist = Depends(get_current_user)
):
    """
    Endpoint para generar estrategias dinámicas según el contexto de la conversación.
    """
    logger.info(f"Generating dynamic strategies: Psych {current_user.id} -> Patient {context.patient_id}")
    try:
        strategies = await generate_strategy_options(context.messages)
        return {"strategies": strategies}
    except Exception as e:
        logger.error(f"Error generating strategies: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate strategies")


class IaPatientRespondRequest(BaseModel):
    patient_id: int

@router.post("/ia-patient/respond")
async def ia_patient_respond(
    req: IaPatientRespondRequest,
    session: Session = Depends(get_session),
    current_user: Psychologist = Depends(get_current_user)
):
    """
    Generate a response from the fictional IA patient using Gemma.
    Fetches the chat history, generates a patient response, and saves it as a message.
    """
    from models import Patient, Message
    from auth import verify_patient_access
    from llm_service import generate_ia_patient_response
    
    verify_patient_access(req.patient_id, current_user, session)
    
    patient = session.get(Patient, req.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not patient.is_ia_patient:
        raise HTTPException(status_code=400, detail="This endpoint is only for IA patients")
    
    # Fetch recent messages for context
    from sqlmodel import select
    messages_db = session.exec(
        select(Message).where(
            Message.patient_id == req.patient_id,
            Message.psychologist_id == current_user.id,
            Message.deleted_at == None
        ).order_by(Message.created_at)
    ).all()
    
    # Convert to chat format
    chat_history = []
    for m in messages_db:
        role = "user" if m.is_from_patient else "assistant"
        chat_history.append({"role": role, "content": m.content})
    
    logger.info(f"IA Patient respond: Psych {current_user.id} -> Patient {req.patient_id} ({len(chat_history)} messages)")
    
    # Generate response using Gemma
    response_text = await generate_ia_patient_response(
        chat_history,
        patient_personality_prompt=patient.ia_patient_prompt
    )
    
    # Save as a message from the patient
    new_message = Message(
        content=response_text,
        patient_id=req.patient_id,
        psychologist_id=current_user.id,
        is_from_patient=True,
        read=False
    )
    session.add(new_message)
    session.commit()
    session.refresh(new_message)
    
    logger.info(f"IA Patient message saved: ID {new_message.id}")
    
    return {
        "id": new_message.id,
        "patient_id": new_message.patient_id,
        "content": new_message.content,
        "is_from_patient": True,
        "read": False,
        "created_at": str(new_message.created_at),
        "was_edited_by_human": False,
        "ai_suggestion_log_id": None
    }