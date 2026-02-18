import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session, create_engine, SQLModel
from services import firebase_service
from models import FCMToken

# Mock firebase app
firebase_service._firebase_app = "MOCK"
# Mock logger to avoid clutter
import logging
logging.basicConfig(level=logging.CRITICAL)

# Use memory DB
engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)

def test_session_sharing():
    print("Starting verification test...")
    
    with Session(engine) as session:
        # Create a dummy token 
        token = FCMToken(patient_id=1, token="test_token", device_type="android")
        session.add(token)
        session.commit()
    
    # Simulate Scheduler Context
    with Session(engine) as outer_session:
        print("Opened outer session (simulating scheduler)...")
        
        # Modify something to ensure transaction is active
        # (Simulating cleanup_previous_completions)
        # token = outer_session.exec(select(FCMToken)).first()
        # token.device_type = "ios"
        # outer_session.add(token)
        
        try:
            print("Calling send_push_to_patient WITH session...")
            # We explicitly want to fail if send_push_notification tries to actually send
            # But we mocked _firebase_app, so send_push_to_patient will proceed to query tokens
            # and then call send_push_notification.
            
            # We need to mock send_push_notification entirely to avoid network/auth errors
            original_send = firebase_service.send_push_notification
            firebase_service.send_push_notification = lambda token, title, body, data: True
            
            count = firebase_service.send_push_to_patient(
                patient_id=1,
                title="Test",
                body="Body",
                session=outer_session
            )
            
            print(f"Success! Processed {count} notifications using shared session.")
            
            # Verify no rollback happened (token should still exist)
            tokens = outer_session.exec(select(FCMToken)).all()
            assert len(tokens) == 1
            
            # Restore
            firebase_service.send_push_notification = original_send
            
        except TypeError as e:
            print(f"FAILED: Function signature mismatch? {e}")
        except Exception as e:
            print(f"FAILED: Unexpected error: {e}")

if __name__ == "__main__":
    from sqlmodel import select # Import here to avoid circular issues
    test_session_sharing()
