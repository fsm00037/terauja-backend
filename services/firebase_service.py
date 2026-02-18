"""
Firebase Cloud Messaging Service for push notifications
"""
import os
import logging
from typing import Optional, List
import firebase_admin
from firebase_admin import credentials, messaging
from sqlmodel import Session, select
from database import engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("firebase_service")

# Firebase app instance
_firebase_app: Optional[firebase_admin.App] = None


def initialize_firebase() -> bool:
    """
    Initialize Firebase Admin SDK with service account credentials.
    Returns True if initialization was successful, False otherwise.
    """
    global _firebase_app
    
    if _firebase_app is not None:
        logger.info("Firebase already initialized")
        return True
    
    # Path to service account JSON file
    service_account_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "psicouja-b1ef9-firebase-adminsdk-fbsvc-cd3f93d439.json"
    )
    
    if not os.path.exists(service_account_path):
        logger.error(f"Firebase service account file not found: {service_account_path}")
        return False
    
    try:
        cred = credentials.Certificate(service_account_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        return False


def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: Optional[dict] = None
) -> bool:
    """
    Send a push notification to a single device.
    
    Args:
        token: FCM device token
        title: Notification title
        body: Notification body text
        data: Optional data payload (key-value pairs)
    
    Returns:
        True if notification was sent successfully, False otherwise.
    """
    if _firebase_app is None:
        logger.error("Firebase not initialized")
        return False
    
    try:
        # Include BOTH notification and data fields:
        # - notification: triggers OS-level display when app is in background (required for iOS)
        # - data: carries metadata for click routing (type, id, click_action)
        # The service worker should NOT manually showNotification since the browser
        # auto-displays from the notification field in background.
        # In foreground, onMessage intercepts and shows a toast instead.
        message_data = {**(data or {}), "title": title, "body": body}
        
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=message_data,
            token=token,
            webpush=messaging.WebpushConfig(
                fcm_options=messaging.WebpushFCMOptions(
                    link="https://s5-ceatic.ujaen.es:8009/"
                )
            )
        )
        
        response = messaging.send(message)
        logger.info(f"[FIREBASE] Push notification sent successfully. Message ID: {response}")
        return True
        
    except messaging.UnregisteredError:
        logger.warning(f"[FIREBASE] Token is invalid/unregistered: {token[:20]}...")
        # Token should be removed from database
        return False
    except Exception as e:
        logger.error(f"[FIREBASE] Failed to send push notification: {type(e).__name__}: {e}")
        return False


def _send_push_to_patient_logic(
    session: Session,
    patient_id: int,
    title: str,
    body: str,
    data: Optional[dict] = None
) -> int:
    """Internal logic for sending push to patient using an active session"""
    from models import FCMToken
    
    # Get all FCM tokens for this patient
    statement = select(FCMToken).where(FCMToken.patient_id == patient_id)
    tokens = session.exec(statement).all()
    
    logger.info(f"[FIREBASE] Found {len(tokens)} tokens for patient {patient_id}")
    
    if not tokens:
        logger.warning(f"[FIREBASE] No FCM tokens found for patient {patient_id}. Notification '{title}' will NOT be delivered via push.")
        return 0
    
    success_count = 0
    tokens_to_remove: List[FCMToken] = []
    
    for token_record in tokens:
        logger.info(f"[FIREBASE] Attempting to send to token: {token_record.token[:20]}...")
        result = send_push_notification(
            token=token_record.token,
            title=title,
            body=body,
            data=data
        )
        
        if result:
            success_count += 1
            logger.info(f"[FIREBASE] Successfully sent to token {token_record.id}")
        else:
            # Mark invalid tokens for removal
            tokens_to_remove.append(token_record)
            logger.warning(f"[FIREBASE] Failed to send to token {token_record.id}, marking for removal")
    
    # Remove invalid tokens
    for invalid_token in tokens_to_remove:
        session.delete(invalid_token)
    
    if tokens_to_remove:
        # Only commit if we own the session? 
        # Actually, if we are passed a session, we might NOT want to commit partial changes if the caller handles atomic commit.
        # But here we are just cleaning up tokens. It's probably safe to flush or commit, 
        # BUT standard practice with injected session is to let caller commit or use flush.
        # However, for token cleanup, we probably want it to persist even if main transaction fails? 
        # No, if main transaction fails, we rollout back everything.
        # So we should NOT commit here if session is injected.
        session.add_all(tokens_to_remove) # Make sure they are marked for deletion
        # We rely on caller to commit if session is injected.
        pass

    # Note: The original code committed deletions.
    # To maintain behavior for "own session" vs "injected session", we handle that in the wrapper.
    return success_count, tokens_to_remove


def send_push_to_patient(
    patient_id: int,
    title: str,
    body: str,
    data: Optional[dict] = None,
    session: Optional[Session] = None
) -> int:
    """
    Send a push notification to all registered devices of a patient.
    
    Args:
        patient_id: Patient ID
        title: Notification title
        body: Notification body text
        data: Optional data payload
        session: Optional SQLModel session. If provided, uses this session and DOES NOT commit.
                 If not provided, creates a new session and COMMITS changes (token cleanup).
    
    Returns:
        Number of successful notifications sent.
    """
    logger.info(f"[FIREBASE] send_push_to_patient called for patient {patient_id}")
    
    if _firebase_app is None:
        logger.error("[FIREBASE] ERROR: Firebase not initialized")
        return 0
        
    if session:
        count, _ = _send_push_to_patient_logic(session, patient_id, title, body, data)
        return count
    else:
        with Session(engine) as new_session:
            count, tokens_removed = _send_push_to_patient_logic(new_session, patient_id, title, body, data)
            if tokens_removed:
                new_session.commit()
                logger.info(f"[FIREBASE] Removed {len(tokens_removed)} invalid FCM tokens")
            return count


def send_new_message_notification(patient_id: int, message_id: int, sender_name: str, session: Optional[Session] = None) -> int:
    """
    Send a notification for a new message.
    """
    return send_push_to_patient(
        patient_id=patient_id,
        title="Nuevo Mensaje",
        body=f"Has recibido un mensaje de {sender_name}",
        data={
            "type": "message", 
            "id": str(message_id),
            "click_action": "/chat"
        },
        session=session
    )


def send_questionnaire_assigned_notification(patient_id: int, assignment_id: int, questionnaire_title: str, session: Optional[Session] = None) -> int:
    """
    Send a notification for a new questionnaire assignment.
    """
    return send_push_to_patient(
        patient_id=patient_id,
        title="Nuevo Cuestionario",
        body=f"Tienes un nuevo cuestionario pendiente: {questionnaire_title}",
        data={
            "type": "questionnaire", 
            "id": str(assignment_id),
            "click_action": "/formularios"
        },
        session=session
    )
