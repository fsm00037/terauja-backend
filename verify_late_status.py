
import sys
import os
from datetime import datetime, timedelta, timezone
from sqlmodel import SQLModel, create_engine, Session, select, Field
from sqlalchemy.pool import StaticPool

# Add backend to sys.path
sys.path.append(os.getcwd())

# Import models
from models import Patient, Questionnaire, Assignment, QuestionnaireCompletion, Psychologist

def verify_late_logic():
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

        q1 = Questionnaire(title="as", icon="file")
        session.add(q1)
        session.flush()

        # Assignment with 2 hour deadline
        assign_main = Assignment(
            patient_id=patient.id, 
            questionnaire_id=q1.id, 
            status="active", 
            assigned_at=datetime.now(),
            deadline_hours=2,
            frequency_type="weekly"
        )
        session.add(assign_main)
        session.flush()
        
        # Scenario 1: On Schedule (Not Late)
        # Scheduled: 3 hours ago
        # Completed: 2.5 hours ago (Within 2h deadline? No wait. Scheduled at T-3h. Deadline T-1h. Completed T-2.5h is valid.
        # Wait: Deadline starts counting from SCHEDULED time.
        # Scheduled: T-3h. Deadline: T-1h (T-3h + 2h). 
        # Completed: T-2.5h. T-2.5h < T-1h? -2.5 < -1. True. So it is on time.
        
        comp_ontime = QuestionnaireCompletion(
            assignment_id=assign_main.id,
            patient_id=patient.id,
            questionnaire_id=q1.id,
            scheduled_at=datetime.now() - timedelta(hours=3),
            completed_at=datetime.now() - timedelta(hours=2), # 1 hour after schedule
            status="completed"
        )
        # Manually trigger logic check simulation
        
        # Scenario 2: Late
        # Scheduled: 5 hours ago
        # Deadline: 2 hours (Expire at T-3h)
        # Completed: 1 hour ago (Late by 2 hours)
        
        comp_late = QuestionnaireCompletion(
            assignment_id=assign_main.id,
            patient_id=patient.id,
            questionnaire_id=q1.id,
            scheduled_at=datetime.now() - timedelta(hours=5),
            completed_at=datetime.now() - timedelta(hours=1),
            status="completed"
        )
        
        # Scenario 3: 0-Hour Deadline (Immediate)
        assign_zero = Assignment(
            patient_id=patient.id, 
            questionnaire_id=q1.id, 
            status="active", 
            assigned_at=datetime.now(),
            deadline_hours=0, # Strict deadline
            frequency_type="weekly"
        )
        session.add(assign_zero)
        session.flush()

        comp_zero_late = QuestionnaireCompletion(
            assignment_id=assign_zero.id,
            patient_id=patient.id,
            questionnaire_id=q1.id,
            scheduled_at=datetime.now() - timedelta(minutes=10),
            completed_at=datetime.now() - timedelta(minutes=5), # 5 mins late
            status="completed"
        )
        session.add(comp_zero_late)
        
        session.add(comp_ontime)
        session.add(comp_late)
        session.commit()
        
        print("\n--- Verifying Logic ---")
        
        def check_is_delayed(c):
             # Logic copied from router
            if c.completed_at and c.scheduled_at and c.assignment:
                deadline_hours = c.assignment.deadline_hours if c.assignment.deadline_hours is not None else 24
                
                sched = c.scheduled_at.replace(tzinfo=None) if c.scheduled_at else None
                comp = c.completed_at.replace(tzinfo=None) if c.completed_at else None
                
                if sched and comp and comp > sched + timedelta(hours=deadline_hours):
                     return True
            return False

        is_late_ontime = check_is_delayed(comp_ontime)
        is_late_late = check_is_delayed(comp_late)
        
        print(f"Scenario 1 (On Time): Expected False, Got {is_late_ontime}")
        print(f"Scenario 2 (Late):    Expected True,  Got {is_late_late}")
        
        if not is_late_ontime and is_late_late:
            print("\nSUCCESS: Logic correctly identifies standard late assignments.")
        else:
            print("\nFAILURE: Standard logic is incorrect.")
            sys.exit(1)
            
        print(f"Scenario 3 (0-Hour Deadline): Expected True")
        is_late_zero = check_is_delayed(comp_zero_late)
        print(f"Got: {is_late_zero}")
        
        if is_late_zero:
             print("SUCCESS: 0-Hour deadline correctly identified as late.")
        else:
             print("FAILURE: 0-Hour deadline treated as on-time (24h bug?).")
             sys.exit(1)

if __name__ == "__main__":
    verify_late_logic()
