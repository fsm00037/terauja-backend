import asyncio
from datetime import datetime, timedelta
from sqlmodel import Session, select, or_
from database import engine
from models import QuestionnaireCompletion, Assignment, Questionnaire
from services.firebase_service import send_questionnaire_assigned_notification
from utils.assignment_utils import cleanup_previous_completions
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")

async def run_scheduler():
    logger.info("Starting background scheduler...")
    while True:
        try:
            with Session(engine) as session:
                now = datetime.utcnow()
                
                # 1. Process 'pending' items that are due (scheduled_at <= now)
                statement_pending = (
                    select(QuestionnaireCompletion, Assignment)
                    .join(Assignment)
                    .where(QuestionnaireCompletion.status == "pending")
                    .where(QuestionnaireCompletion.scheduled_at <= now)
                )
                pending_items = session.exec(statement_pending).all()
                
                count_sent = 0
                count_paused_skipped = 0
                notifications_to_send = []

                for completion, assignment in pending_items:
                    if assignment.status == "paused":
                        completion.status = "paused" # Mark as paused if parent is paused
                        count_paused_skipped += 1
                    else:
                        cleanup_previous_completions(session, completion.patient_id, completion.questionnaire_id, exclude_completion_id=completion.id)
                        completion.status = "sent"
                        count_sent += 1
                        # Queue notification for this patient
                        notifications_to_send.append({
                            "patient_id": completion.patient_id,
                            "questionnaire_id": completion.questionnaire_id,
                            "assignment_id": completion.assignment_id
                        })
                    session.add(completion)
                
                # 2. Mark 'sent' as 'missed' if scheduled_at + 24h <= now
                # Note: Adjust logic if you want to allow late completions, but user requested missed.
                expiration_time = now - timedelta(hours=24)
                statement_expired = (
                    select(QuestionnaireCompletion)
                    .where(QuestionnaireCompletion.status == "sent")
                    .where(QuestionnaireCompletion.scheduled_at <= expiration_time)
                )
                expired_to_missed = session.exec(statement_expired).all()
                
                count_missed = 0
                for c in expired_to_missed:
                    c.status = "missed"
                    session.add(c)
                    count_missed += 1
                
                if count_sent > 0 or count_missed > 0:
                    session.commit()
                    logger.info(f"Scheduler update: Sent {count_sent}, Missed {count_missed}, Paused {count_paused_skipped}")
                    
                    # Send push notifications for newly sent questionnaires
                    for notif in notifications_to_send:
                        try:
                            # Get questionnaire title
                            questionnaire = session.get(Questionnaire, notif["questionnaire_id"])
                            title = questionnaire.title if questionnaire else "Cuestionario"
                            
                            logger.info(f"Sending notification for patient {notif['patient_id']}, assignment {notif['assignment_id']}")
                            
                            send_questionnaire_assigned_notification(
                                patient_id=notif["patient_id"],
                                assignment_id=notif["assignment_id"],
                                questionnaire_title=title
                            )
                        except Exception as push_error:
                            logger.error(f"Failed to send push notification: {push_error}")
                    
        except Exception as e:
            logger.error(f"Error in scheduler: {e}")
            
        # Wait for 1 minute before next check
        await asyncio.sleep(60)
