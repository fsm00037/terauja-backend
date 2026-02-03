
import sys
import os
from datetime import datetime, timedelta, timezone
from sqlmodel import SQLModel, create_engine, Session, select, Field
from sqlalchemy.orm import selectinload

# Add backend to sys.path
sys.path.append(os.getcwd())

# Import models
from models import Patient, Questionnaire, Assignment, QuestionnaireCompletion, Psychologist

def check_db():
    from database import engine

    with Session(engine) as session:
        # Fetch last 5 completions
        try:
            # Just get ONE
            c = session.exec(select(QuestionnaireCompletion).options(selectinload(QuestionnaireCompletion.assignment)).order_by(QuestionnaireCompletion.completed_at.desc()).limit(1)).first()
            if c:
                print(f"LAST ITEM ID: {c.id}", flush=True)
                print(f"Scheduled: {c.scheduled_at}", flush=True)
                print(f"Completed: {c.completed_at}", flush=True)
                print(f"Deadline: {c.assignment.deadline_hours if c.assignment else 'N/A'}", flush=True)
                print(f"Is Delayed: {c.is_delayed}", flush=True)
            else:
                print("No completions found.", flush=True)

        except Exception as e:
             print(f"ERROR: {e}", flush=True)

if __name__ == "__main__":
    check_db()
