"""
Notifications router for FCM token registration and push notifications
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from datetime import datetime

from database import get_session
from models import FCMToken, Patient, Psychologist
from auth import get_current_patient, get_current_user
from services.firebase_service import send_push_notification, send_push_to_patient

router = APIRouter()


class FCMTokenRequest(BaseModel):
    token: str


class SendNotificationRequest(BaseModel):
    patient_id: int
    title: str
    body: str


@router.post("/register-token")
def register_fcm_token(
    request: FCMTokenRequest,
    session: Session = Depends(get_session),
    current_patient: Patient = Depends(get_current_patient)
):
    """
    Register an FCM token for the current patient.
    If the token already exists, update its timestamp.
    """
    import logging
    logger = logging.getLogger("notifications")
    print(f"[DEBUG] Register token request received for patient {current_patient.id}")
    # logger.info(f"[FCM] Registering token for patient {current_patient.id}: {request.token[:30]}...")
    
    # Check if token already exists
    existing = session.exec(
        select(FCMToken).where(FCMToken.token == request.token)
    ).first()
    
    if existing:
        # Update existing token (might be from same or different patient)
        existing.patient_id = current_patient.id
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        # logger.info(f"[FCM] Token updated, id={existing.id}")
        return {"message": "Token updated", "token_id": existing.id}
    
    # Create new token
    fcm_token = FCMToken(
        patient_id=current_patient.id,
        token=request.token
    )
    session.add(fcm_token)
    session.commit()
    session.refresh(fcm_token)
    
    # logger.info(f"[FCM] Token registered, id={fcm_token.id}")
    return {"message": "Token registered", "token_id": fcm_token.id}


@router.delete("/unregister-token")
def unregister_fcm_token(
    request: FCMTokenRequest,
    session: Session = Depends(get_session),
    current_patient: Patient = Depends(get_current_patient)
):
    """
    Unregister an FCM token for the current patient.
    """
    existing = session.exec(
        select(FCMToken).where(
            FCMToken.token == request.token,
            FCMToken.patient_id == current_patient.id
        )
    ).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Token not found")
    
    session.delete(existing)
    session.commit()
    
    return {"message": "Token unregistered"}


@router.post("/send")
def send_notification(
    request: SendNotificationRequest,
    session: Session = Depends(get_session),
    current_user: Psychologist = Depends(get_current_user)
):
    """
    Send a push notification to all devices of a patient.
    Admin/Psychologist only endpoint.
    """
    # Verify patient exists
    patient = session.get(Patient, request.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Send notification
    success_count = send_push_to_patient(
        patient_id=request.patient_id,
        title=request.title,
        body=request.body
    )
    
    return {
        "message": f"Notification sent to {success_count} devices",
        "success_count": success_count
    }


@router.post("/test")
def test_notification(
    session: Session = Depends(get_session),
    current_patient: Patient = Depends(get_current_patient)
):
    """
    Send a test notification to the current patient's devices.
    """
    import logging
    logger = logging.getLogger("notifications")
    
    # Debug: Check tokens in DB
    tokens = session.exec(select(FCMToken).where(FCMToken.patient_id == current_patient.id)).all()
    # logger.info(f"[TEST] Patient ID: {current_patient.id}, FCM Tokens count: {len(tokens)}")
    
    # Also check all tokens
    all_tokens = session.exec(select(FCMToken)).all()
    # logger.info(f"[TEST] Total FCM tokens in DB: {len(all_tokens)}")
    
    success_count = send_push_to_patient(
        patient_id=current_patient.id,
        title="Notificación de Prueba",
        body="Esta es una notificación de prueba. ¡Las notificaciones push funcionan correctamente!"
    )
    
    return {
        "message": f"Test notification sent to {success_count} devices",
        "success_count": success_count,
        "patient_id": current_patient.id,
        "tokens_found": len(tokens)
    }
