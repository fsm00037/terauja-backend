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
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=token,
            # Web push-specific configuration
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon="/icon.svg",
                ),
                fcm_options=messaging.WebpushFCMOptions(
                    link="/"
                )
            )
        )
        
        response = messaging.send(message)
        # logger.info(f"Push notification sent successfully: {response}")
        return True
        
    except messaging.UnregisteredError:
        # logger.warning(f"Token is no longer valid: {token[:20]}...")
        # Token should be removed from database
        return False
    except Exception as e:
        logger.error(f"Failed to send push notification: {type(e).__name__}: {e}")
        return False


def send_push_to_patient(
    patient_id: int,
    title: str,
    body: str,
    data: Optional[dict] = None
) -> int:
    """
    Send a push notification to all registered devices of a patient.
    
    Args:
        patient_id: Patient ID
        title: Notification title
        body: Notification body text
        data: Optional data payload
    
    Returns:
        Number of successful notifications sent.
    """
    from models import FCMToken
    
    
    # print(f"[FIREBASE] send_push_to_patient called for patient {patient_id}")
    
    
    if _firebase_app is None:
        # print("[FIREBASE] ERROR: Firebase not initialized")
        logger.error("Firebase not initialized")
        return 0
    
    with Session(engine) as session:
        # Get all FCM tokens for this patient
        statement = select(FCMToken).where(FCMToken.patient_id == patient_id)
        tokens = session.exec(statement).all()
        
        # print(f"[FIREBASE] Found {len(tokens)} tokens for patient {patient_id}")
        
        
        if not tokens:
            logger.info(f"No FCM tokens found for patient {patient_id}")
            return 0
        
        success_count = 0
        tokens_to_remove: List[FCMToken] = []
        
        for token_record in tokens:
            result = send_push_notification(
                token=token_record.token,
                title=title,
                body=body,
                data=data
            )
            
            if result:
                success_count += 1
            else:
                # Mark invalid tokens for removal
                tokens_to_remove.append(token_record)
        
        # Remove invalid tokens
        for invalid_token in tokens_to_remove:
            session.delete(invalid_token)
        
        if tokens_to_remove:
            session.commit()
            logger.info(f"Removed {len(tokens_to_remove)} invalid FCM tokens")
        
        logger.info(f"Sent {success_count}/{len(tokens)} notifications to patient {patient_id}")
        return success_count
