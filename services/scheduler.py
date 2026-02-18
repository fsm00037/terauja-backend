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
                    .order_by(QuestionnaireCompletion.scheduled_at)
                )
                pending_items = session.exec(statement_pending).all()
                
                count_sent = 0
                count_paused_skipped = 0

                for completion, assignment in pending_items:
                    try:
                        # 1. Update status logic
                        if assignment.status == "paused":
                            completion.status = "paused"
                            session.add(completion)
                            session.commit()
                            count_paused_skipped += 1
                            continue

                        # 2. Cleanup previous
                        cleanup_previous_completions(
                            session, 
                            completion.patient_id, 
                            completion.questionnaire_id, 
                            exclude_completion_id=completion.id,
                            current_assignment_id=completion.assignment_id,
                            older_than=completion.scheduled_at
                        )
                        
                        # 3. Update status and Commit FIRST
                        # This releases the DB lock so that the notification service can open a new connection/session safely.
                        completion.status = "sent"
                        session.add(completion)
                        session.commit()
                        session.refresh(completion)
                        count_sent += 1
                        
                        # 4. Send Notification (Best Effort)
                        try:
                            # Get questionnaire title
                            questionnaire = session.get(Questionnaire, completion.questionnaire_id)
                            title = questionnaire.title if questionnaire else "Cuestionario"
                            
                            logger.info(f"Sending notification for patient {completion.patient_id}, assignment {completion.assignment_id}")
                            
                            # Ensure firebase is init (safe to call multiple times)
                            from services.firebase_service import initialize_firebase
                            initialize_firebase()
                            
                            # No need to pass 'session', let it create its own short-lived session
                            sent_count = send_questionnaire_assigned_notification(
                                patient_id=completion.patient_id,
                                assignment_id=completion.assignment_id,
                                questionnaire_title=title
                            )
                            logger.info(f"Notification result for {completion.id}: Sent to {sent_count} devices")
                        except Exception as push_error:
                            logger.error(f"Failed to send push notification: {push_error}")
                            import traceback
                            traceback.print_exc()
                            with open("scheduler_error.log", "a") as f:
                                f.write(f"{datetime.utcnow()} - Error sending push: {push_error}\n")
                        
                    except Exception as item_error:
                        logger.error(f"Error processing completion {completion.id}: {item_error}")
                        session.rollback() # Rollback this specific item's transaction if DB failed
                
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
                
                if count_missed > 0:
                    session.commit()
                
                if count_sent > 0 or count_missed > 0 or count_paused_skipped > 0:
                    logger.info(f"Scheduler update: Sent {count_sent}, Missed {count_missed}, Paused {count_paused_skipped}")
                    
        except Exception as e:
            logger.error(f"Error in scheduler: {e}")
            
        # Wait for 1 minute before next check
        await asyncio.sleep(60)
