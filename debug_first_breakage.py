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

def test_first_breakage():
    with Session(engine) as session:
        # Setup Data
        p_id = 1
        q_id = 1
        now = datetime.utcnow()
        
        # Create Assignment (ID 100)
        a1 = Assignment(id=100, patient_id=p_id, questionnaire_id=q_id, status="active")
        session.add(a1)
        
        # 1. First item (Scheduled Now) - The one we send
        c1 = QuestionnaireCompletion(
            id=1,
            patient_id=p_id, questionnaire_id=q_id, assignment_id=100,
            status="pending", scheduled_at=now,
            deleted_at=None
        )
        
        # 2. Future item (One hour later)
        c2 = QuestionnaireCompletion(
            id=2,
            patient_id=p_id, questionnaire_id=q_id, assignment_id=100,
            status="pending", scheduled_at=now + timedelta(hours=1),
            deleted_at=None
        )
        
        # 3. Future item (Tomorrow)
        c3 = QuestionnaireCompletion(
            id=3,
            patient_id=p_id, questionnaire_id=q_id, assignment_id=100,
            status="pending", scheduled_at=now + timedelta(days=1),
            deleted_at=None
        )
        
        session.add(c1)
        session.add(c2)
        session.add(c3)
        session.commit()
        
        print("Initial State:")
        for c in [c1, c2, c3]:
            session.refresh(c)
            print(f"Completion {c.id} ({c.scheduled_at}): {c.status}")
            
        # Simulate "Sending" C1 (The First One)
        print(f"\nProcessing C1 (Sending First)...")
        
        cleanup_previous_completions(
            session=session,
            patient_id=p_id,
            questionnaire_id=q_id,
            exclude_completion_id=c1.id,
            older_than=c1.scheduled_at,
            current_assignment_id=c1.assignment_id
        )
        session.commit()
        
        session.refresh(a1)
        print(f"\nPost-Cleanup State:")
        print(f"Assignment 100 Deleted: {a1.deleted_at}")
        
        for c in [c1, c2, c3]:
            session.refresh(c)
            deleted_str = "DELETED" if c.deleted_at else "Active"
            print(f"Completion {c.id}: {deleted_str}")
            
        if a1.deleted_at:
            print("\nFAILURE: Assignment was deleted!")
        else:
            print("\nSUCCESS: Assignment persists.")
            
        if c2.deleted_at or c3.deleted_at:
             print("FAILURE: Future items were deleted!")
        else:
             print("SUCCESS: Future items are safe.")

if __name__ == "__main__":
    test_first_breakage()
