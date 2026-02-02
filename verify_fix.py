
import sys
import os
from datetime import datetime, timedelta, timezone
from sqlmodel import SQLModel, create_engine, Session, select, Field
from sqlalchemy.pool import StaticPool

# Add backend to sys.path
sys.path.append(os.getcwd())

# Import models and utils
from models import Patient, Questionnaire, Assignment, QuestionnaireCompletion, Psychologist
from utils.assignment_utils import cleanup_previous_completions

def verify_fix():
    # Setup In-Memory DB
    engine = create_engine(
        "sqlite://", 
        connect_args={"check_same_thread": False}, 
        poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # 1. Create Data
        psych = Psychologist(name="Dr. Test", email="test@test.com", password="hash", role="psychologist")
        session.add(psych)
        session.flush()

        patient = Patient(patient_code="P001", access_code="1234", psychologist_id=psych.id)
        session.add(patient)
        session.flush()

        q1 = Questionnaire(title="Q1", icon="file")
        session.add(q1)
        session.flush()

        # --- Scenario: Three Scheduled Assignments ---
        # 0. Old (Yesterday) - Should be deleted
        # 1. Current (Now)   - Triggering the cleanup
        # 2. Future (Tomorrow) - Should be preserved
        
        assign_main = Assignment(patient_id=patient.id, questionnaire_id=q1.id, status="active", assigned_at=datetime.utcnow())
        session.add(assign_main)
        session.flush()

        comp_old = QuestionnaireCompletion(
            assignment_id=assign_main.id,
            patient_id=patient.id,
            questionnaire_id=q1.id,
            scheduled_at=datetime.utcnow() - timedelta(days=1),
            status="pending" # Was pending, missed, etc.
        )
        session.add(comp_old)

        comp_current = QuestionnaireCompletion(
            assignment_id=assign_main.id,
            patient_id=patient.id,
            questionnaire_id=q1.id,
            scheduled_at=datetime.utcnow() - timedelta(minutes=10), # Due now
            status="pending"
        )
        session.add(comp_current)
        
        comp_future = QuestionnaireCompletion(
            assignment_id=assign_main.id,
            patient_id=patient.id,
            questionnaire_id=q1.id,
            scheduled_at=datetime.utcnow() + timedelta(days=1), # Due tomorrow
            status="pending"
        )
        session.add(comp_future)
        session.commit()

        print(f"Initial State:")
        print(f"Comp Old:    ID={comp_old.id}, Scheduled={comp_old.scheduled_at}")
        print(f"Comp Current: ID={comp_current.id}, Scheduled={comp_current.scheduled_at}")
        print(f"Comp Future: ID={comp_future.id}, Scheduled={comp_future.scheduled_at}")

        # 2. Simulate processing of Comp Current
        print("\nProcessing Comp Current -> mark as sent and cleanup...")
        comp_current.status = "sent"
        session.add(comp_current)
        
        # Call cleanup WITH timestamp
        cleanup_previous_completions(
            session, 
            comp_current.patient_id, 
            comp_current.questionnaire_id, 
            exclude_completion_id=comp_current.id,
            older_than=comp_current.scheduled_at
        )
        session.commit()
        
        # 3. Verify Result
        session.refresh(comp_old)
        session.refresh(comp_current)
        session.refresh(comp_future)
        
        print(f"\nFinal State:")
        print(f"Comp Old:     ID={comp_old.id}, Deleted={comp_old.deleted_at}")
        print(f"Comp Current: ID={comp_current.id}, Deleted={comp_current.deleted_at}")
        print(f"Comp Future:  ID={comp_future.id}, Deleted={comp_future.deleted_at}")
        
        success = True
        
        if comp_old.deleted_at is None:
            print("FAILURE: Old assignment was NOT deleted.")
            success = False
        else:
             print("SUCCESS: Old assignment was deleted.")
             
        if comp_future.deleted_at is not None:
             print("FAILURE: Future assignment WAS deleted (Bug persists).")
             success = False
        else:
             print("SUCCESS: Future assignment was preserved.")
             
        if success:
            print("\nVERIFICATION SUCCESSFUL: Logic is correct.")
        else:
            print("\nVERIFICATION FAILED.")

if __name__ == "__main__":
    verify_fix()
