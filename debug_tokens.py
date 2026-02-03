from sqlmodel import Session, select, func
from database import engine
from models import FCMToken, Patient

def check_tokens():
    with Session(engine) as session:
        # Group tokens by patient
        patients = session.exec(select(Patient)).all()
        print(f"Total Patients: {len(patients)}")
        
        for patient in patients:
            tokens = session.exec(select(FCMToken).where(FCMToken.patient_id == patient.id)).all()
            if len(tokens) > 1:
                print(f"WARNING: Patient {patient.id} ({patient.patient_code}) has {len(tokens)} tokens!")
                for t in tokens:
                    print(f" - Token ID: {t.id}, Updated: {t.updated_at}, Token: {t.token[:20]}...")
            elif len(tokens) == 1:
                 print(f"Patient {patient.id} has 1 token.")
            else:
                 pass # No tokens

if __name__ == "__main__":
    check_tokens()
