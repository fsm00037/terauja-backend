from sqlmodel import Session, select
from database import engine
from models import Psychologist
from auth import hash_password

def create_superadmin():
    with Session(engine) as session:
        # Check if superadmin already exists
        statement = select(Psychologist).where(Psychologist.role == "superadmin")
        results = session.exec(statement)
        superadmin = results.first()

        if superadmin:
            print(f"Superadmin already exists: {superadmin.email}")
            return

        # Create new superadmin
        new_superadmin = Psychologist(
            name="Super Admin",
            email="superadmin@psicouja.com",
            password=hash_password("superadmin123"),
            role="superadmin",
            schedule="N/A",
            is_online=False
        )
        
        session.add(new_superadmin)
        session.commit()
        session.refresh(new_superadmin)
        
        print(f"Superadmin created successfully!")
        print(f"Email: {new_superadmin.email}")
        print(f"Password: superadmin123")

if __name__ == "__main__":
    create_superadmin()
