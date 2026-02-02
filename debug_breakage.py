from sqlmodel import Session, SQLModel, create_engine, select
from datetime import datetime, timedelta, timezone
import sys
import os

# Add backend path to sys.path
sys.path.append(os.getcwd())

from models import QuestionnaireCompletion, Patient, Questionnaire, Assignment
from utils.assignment_utils import cleanup_previous_completions

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)

def test_breakage():
    with Session(engine) as session:
        # Setup Data
        p_id = 1
        q_id = 1
        now = datetime.utcnow()
        
        # Create ONE Assignment with multiple scheduled items (Weekly)
        # Assignment ID = 100
        a1 = Assignment(id=100, patient_id=p_id, questionnaire_id=q_id, status="active")
        session.add(a1)
        
        # 1. Past item (Missed/Pending) - e.g. last week
        # If this exists, it might trigger the cleanup logic
        c1 = QuestionnaireCompletion(
            id=1,
            patient_id=p_id, questionnaire_id=q_id, assignment_id=100,
            status="pending", scheduled_at=now - timedelta(days=7),
            deleted_at=None
        )
        
        # 2. Current item (Due Now)
        c2 = QuestionnaireCompletion(
            id=2,
            patient_id=p_id, questionnaire_id=q_id, assignment_id=100,
            status="pending", scheduled_at=now,
            deleted_at=None
        )
        
        # 3. Future item (Next Week)
        c3 = QuestionnaireCompletion(
            id=3,
            patient_id=p_id, questionnaire_id=q_id, assignment_id=100,
            status="pending", scheduled_at=now + timedelta(days=7),
            deleted_at=None
        )
        
        session.add(c1)
        session.add(c2)
        session.add(c3)
        session.commit()
        
        print("Initial State:")
        print(f"Assignment 100 Deleted: {a1.deleted_at}")
        for c in [c1, c2, c3]:
            session.refresh(c)
            print(f"Completion {c.id} ({c.scheduled_at}): {c.status} | Deleted: {c.deleted_at}")
            
        # Simulate "Sending" C2 (Current)
        print(f"\nProcessing C2 (Sending)...")
        # In the router, we call cleanup passing C2 details
        
        cleanup_previous_completions(
            session=session,
            patient_id=p_id,
            questionnaire_id=q_id,
            exclude_completion_id=c2.id,
            older_than=c2.scheduled_at,
            current_assignment_id=c2.assignment_id
        )
        session.commit()
        
        session.refresh(a1)
        print(f"\nPost-Cleanup State:")
        print(f"Assignment 100 Deleted: {a1.deleted_at}")
        
        for c in [c1, c2, c3]:
            session.refresh(c)
            print(f"Completion {c.id}: Delete={c.deleted_at}")
            
        if a1.deleted_at:
            print("\nFAILURE: Single assignment was deleted! This breaks future items.")
        else:
            print("\nSUCCESS: Assignment persists.")
            
        # Check if C1 was cleaned up (Desired)
        if c1.deleted_at:
             print("SUCCESS: Old item C1 was cleaned up.")
        else:
             print("FAILURE: Old item C1 was NOT cleaned up.")
             
        # Check if C3 is safe (Desired)
        if not c3.deleted_at:
            print("SUCCESS: Future item C3 is safe.")
        else:
            print("FAILURE: Future item C3 was deleted!")

if __name__ == "__main__":
    test_breakage()
