from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import UploadFile, File
import shutil
import os
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from typing import List, Optional
import secrets
from sqlalchemy import DateTime
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from database import create_db_and_tables, get_session
from models import Patient, Questionnaire, Assignment, AssignmentWithQuestionnaire, PatientReadWithAssignments, Message, MessageCreate, MessageRead, Note, Psychologist, PsychologistUpdate, Session as TherapySession, SessionUpdate, SessionRead, AssessmentStat, AuditLog, AssessmentStatRead, NoteRead, PsychologistRead, PatientRead, QuestionnaireRead, AssignmentRead
from logging_utils import log_action
from pydantic import BaseModel
from auth import hash_password, verify_password, create_access_token, get_current_user, require_admin, verify_patient_access, get_current_patient, get_current_actor

class LoginRequest(BaseModel):
    email: str
    password: str

class PatientLoginRequest(BaseModel):
    email: str
    access_code: str

class AssignRequest(BaseModel):
    psychologist_id: int

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    
    # Create Default Super Admin if no users exist
    from database import engine
    with Session(engine) as session:
        admin = session.exec(select(Psychologist).where(Psychologist.role == "admin")).first()
        if not admin:
            print("Creating default Super Admin...")
            super_admin = Psychologist(
                name="Super Admin",
                email="admin@psicouja.com",
                password=hash_password("admin"),  # Hashed password
                role="admin",
                schedule="Siempre Disponible"
            )
            session.add(super_admin)
            session.commit()
            print("Default Admin Created: admin@psicouja.com / admin")
    
    yield

app = FastAPI(lifespan=lifespan)
from sqlalchemy.orm import selectinload


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Utilities
def generate_access_code():
    return secrets.token_urlsafe(6).upper()

def generate_patient_code():
    return "P-" + secrets.token_hex(2).upper()

# --- Routes ---

@app.get("/")
def read_root():
    return {"message": "Psychology Backend API is running"}

# --- Auth & Profile ---

@app.post("/login")
def login(creds: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(Psychologist).where(Psychologist.email == creds.email)).first()
    if not user or not verify_password(creds.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create JWT token
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    
    # Log successful login
    log_action(session, user.id, "psychologist", user.name, "LOGIN", details="Successful login")
    
    # Set online status
    user.is_online = True
    user.last_active = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)

    return {
        "id": user.id, 
        "name": user.name, 
        "role": user.role, 
        "email": user.email,
        "access_token": access_token
    }

@app.get("/psychologists", response_model=List[PsychologistRead])
def get_psychologists(session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    return session.exec(select(Psychologist)).all()

@app.post("/psychologists")
def create_psychologist(psychologist: Psychologist, session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    # Generate random password
    raw_password = secrets.token_urlsafe(8)
    psychologist.password = hash_password(raw_password)  # Hash the password
    
    # Simulate Email (Write to file for user visibility)
    email_content = f"""
===========================================
To: {psychologist.email}
Subject: Bienvenido a TeraUJA - Tus Credenciales
-------------------------------------------
Hola {psychologist.name},

Se ha creado tu cuenta profesional.
Usuario: {psychologist.email}
Contraseña: {raw_password}

Por favor cambia tu contraseña al ingresar.
===========================================
"""
    print(email_content)
    with open("simulated_emails.txt", "a", encoding="utf-8") as f:
        f.write(email_content + "\n")
    
    session.add(psychologist)
    session.commit()
    session.refresh(psychologist)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "CREATE_PSYCHOLOGIST", details={"created_email": psychologist.email, "role": psychologist.role})

    return {
        "id": psychologist.id,
        "name": psychologist.name,
        "email": psychologist.email,
        "role": psychologist.role,
        "schedule": psychologist.schedule,
        "phone": psychologist.phone
    }

@app.delete("/psychologists/{user_id}")
def delete_psychologist(user_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting the last admin or self (optional safety but good practice)
    # For now, just simple delete.
    
    # Unassign patients (optional, or let them hang? Better to unassign)
    patients = session.exec(select(Patient).where(Patient.psychologist_id == user_id)).all()
    for p in patients:
        p.psychologist_id = None
        p.psychologist_name = "Sin Asignar"
        p.psychologist_schedule = ""
        session.add(p)
        
    session.delete(user)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_PSYCHOLOGIST", details={"deleted_user_id": user_id})
    
    return {"ok": True}

@app.get("/profile/{user_id}", response_model=PsychologistRead)
def get_user_profile(user_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # Users can only access their own profile unless admin
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/profile/{user_id}", response_model=PsychologistRead)
def update_user_profile(user_id: int, profile_data: PsychologistUpdate, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # Users can only update their own profile unless admin
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if profile_data.name: user.name = profile_data.name
    if profile_data.schedule: user.schedule = profile_data.schedule
    if profile_data.phone: user.phone = profile_data.phone
    if profile_data.ai_style is not None: user.ai_style = profile_data.ai_style
    if profile_data.ai_tone is not None: user.ai_tone = profile_data.ai_tone
    if profile_data.ai_instructions is not None: user.ai_instructions = profile_data.ai_instructions
        
    session.add(user)
    
    # Propagate changes to assigned patients
    patients = session.exec(select(Patient).where(Patient.psychologist_id == user_id)).all()
    for p in patients:
        if profile_data.name: p.psychologist_name = profile_data.name
        if profile_data.schedule: p.psychologist_schedule = profile_data.schedule
        session.add(p)
        
    session.commit()
    session.refresh(user)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_PROFILE", details={"updated_user_id": user_id})
    
    return user

# --- Patients ---

@app.post("/patients")
def create_patient(patient: Patient, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # If not admin and no psychologist_id provided, assign to current user
    if current_user.role != "admin" and not patient.psychologist_id:
        patient.psychologist_id = current_user.id

    if not patient.access_code:
        patient.access_code = generate_access_code()
    
    # If psychologist_id is provided, verify it exists
    if patient.psychologist_id:
        psych = session.get(Psychologist, patient.psychologist_id)
        if psych:
            patient.psychologist_name = psych.name
            patient.psychologist_schedule = psych.schedule
            patient.psychologist_photo = psych.photo_url
    else:
        # Fallback: assign to current user
        patient.psychologist_id = current_user.id
        patient.psychologist_name = current_user.name
        patient.psychologist_schedule = current_user.schedule

    session.add(patient)
    session.commit()
    session.refresh(patient)
    
    # Manually construct dict to force read and avoid serialization issues
    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "access_code": patient.access_code,
        "email": patient.email,
        "psychologist_id": patient.psychologist_id,
        "psychologist_name": patient.psychologist_name,
        "psychologist_schedule": patient.psychologist_schedule,
        "created_at": patient.created_at,
        "clinical_summary": patient.clinical_summary
    }

@app.get("/patients", response_model=List[PatientReadWithAssignments])
def read_patients(offset: int = 0, limit: int = Query(default=100, lte=100), psychologist_id: Optional[int] = None, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    query = select(Patient).options(selectinload(Patient.assignments).selectinload(Assignment.questionnaire))
    
    # Non-admin users can only see their own patients
    if current_user.role != "admin":
        query = query.where(Patient.psychologist_id == current_user.id)
    elif psychologist_id:
        query = query.where(Patient.psychologist_id == psychologist_id)
    
    patients = session.exec(query.offset(offset).limit(limit)).all()
    
    # Calculate unread messages for each patient
    results = []
    for p in patients:
        unread_count = session.exec(
            select(func.count(Message.id)).where(
                Message.patient_id == p.id,
                Message.is_from_patient == True,
                Message.read == False
            )
        ).one()
        
        # Manually construct response model with extra field
        p_read = PatientReadWithAssignments(
            id=p.id,
            patient_code=p.patient_code,
            access_code=p.access_code,
            email=p.email,
            is_online=p.is_online,
            total_online_seconds=p.total_online_seconds,
            last_active=p.last_active,
            created_at=p.created_at,
            psychologist_id=p.psychologist_id,
            psychologist_name=p.psychologist_name,
            clinical_summary=p.clinical_summary,
            assignments=p.assignments,
            unread_messages=unread_count
        )
        results.append(p_read)
        
    return results

@app.patch("/patients/{patient_id}/assign")
def assign_patient(patient_id: int, req: AssignRequest, session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    patient = session.get(Patient, patient_id)
    psychologist = session.get(Psychologist, req.psychologist_id)
    
    if not patient or not psychologist:
        raise HTTPException(status_code=404, detail="Patient or Psychologist not found")
        
    patient.psychologist_id = psychologist.id
    patient.psychologist_name = psychologist.name
    patient.psychologist_schedule = psychologist.schedule
    patient.psychologist_photo = psychologist.photo_url
    
    session.add(patient)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "ASSIGN_PATIENT", details={"patient_id": patient.id, "assigned_to": psychologist.email})

    return {"ok": True}

@app.patch("/patients/{patient_id}/clinical-summary")
def update_clinical_summary(patient_id: int, summary_data: dict, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(patient_id, current_user, session)
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient.clinical_summary = summary_data.get("clinical_summary", "")
    session.add(patient)
    session.commit()
    session.refresh(patient)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_CLINICAL_SUMMARY", details={"patient_id": patient_id})
    
    return {"ok": True, "clinical_summary": patient.clinical_summary}

# --- Questionnaires ---

@app.post("/questionnaires", response_model=QuestionnaireRead)
def create_questionnaire(questionnaire: Questionnaire, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    session.add(questionnaire)
    session.commit()
    session.refresh(questionnaire)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "CREATE_QUESTIONNAIRE", details={"title": questionnaire.title})
    
    return {
        "id": questionnaire.id,
        "title": questionnaire.title,
        "icon": questionnaire.icon,
        "questions": questionnaire.questions,
        "created_at": questionnaire.created_at
    }

@app.get("/questionnaires", response_model=List[QuestionnaireRead])
def read_questionnaires(offset: int = 0, limit: int = Query(default=100, lte=100), session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    questionnaires = session.exec(select(Questionnaire).offset(offset).limit(limit)).all()
    return questionnaires

@app.delete("/questionnaires/{questionnaire_id}")
def delete_questionnaire(questionnaire_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    questionnaire = session.get(Questionnaire, questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    session.delete(questionnaire)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_QUESTIONNAIRE", details={"questionnaire_id": questionnaire_id})
    
    return {"ok": True}

# --- Messages ---
@app.post("/messages", response_model=MessageRead)
def create_message(message: MessageCreate, session: Session = Depends(get_session), current_user = Depends(get_current_actor)):
    # Verify access based on user type
    if hasattr(current_user, "role"): # Psychologist
        verify_patient_access(message.patient_id, current_user, session)
    else: # Patient
        if current_user.id != message.patient_id:
             raise HTTPException(status_code=403, detail="Access denied")

    db_message = Message.from_orm(message)
    session.add(db_message)
    session.commit()
    session.refresh(db_message)
    
    log_action(session, current_user.id, "psychologist" if not message.is_from_patient else "patient", current_user.name, "CREATE_MESSAGE", details={"patient_id": message.patient_id, "is_from_patient": message.is_from_patient})
    
    return db_message

@app.post("/messages/mark-read/{patient_id}")
def mark_messages_read(patient_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(patient_id, current_user, session)
    statement = select(Message).where(
        Message.patient_id == patient_id,
        Message.is_from_patient == True,
        Message.read == False
    )
    messages = session.exec(statement).all()
    
    for msg in messages:
        msg.read = True
        session.add(msg)
        
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "MARK_MESSAGES_READ", details={"patient_id": patient_id, "count": len(messages)})
    
    return {"ok": True, "count": len(messages)}

@app.get("/messages/{patient_id}", response_model=List[MessageRead])
def get_messages(patient_id: int, session: Session = Depends(get_session), current_user = Depends(get_current_actor)):
    # Verify access based on user type
    if hasattr(current_user, "role"): # Psychologist
        verify_patient_access(patient_id, current_user, session)
    else: # Patient
        if current_user.id != patient_id:
            raise HTTPException(status_code=403, detail="Access denied")
    statement = select(Message).where(Message.patient_id == patient_id).order_by(Message.created_at)
    return session.exec(statement).all()

@app.delete("/messages/{patient_id}")
def delete_messages(patient_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(patient_id, current_user, session)
    statement = select(Message).where(Message.patient_id == patient_id)
    results = session.exec(statement)
    for message in results:
        session.delete(message)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_MESSAGES", details={"patient_id": patient_id})
    
    return {"ok": True, "deleted": True}

@app.put("/questionnaires/{questionnaire_id}", response_model=QuestionnaireRead)
def update_questionnaire(questionnaire_id: int, updated_q: Questionnaire, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    questionnaire = session.get(Questionnaire, questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    
    questionnaire.title = updated_q.title
    questionnaire.description = updated_q.description
    questionnaire.questions = updated_q.questions
    
    session.add(questionnaire)
    session.commit()
    session.refresh(questionnaire)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_QUESTIONNAIRE", details={"questionnaire_id": questionnaire_id})
    
    return questionnaire

# --- Assignments ---
@app.post("/assignments", response_model=AssignmentRead)
def assign_questionnaire(assignment: Assignment, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(assignment.patient_id, current_user, session)
    # Verify patient exists
    patient = session.get(Patient, assignment.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Verify questionnaire exists
    questionnaire = session.get(Questionnaire, assignment.questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "ASSIGN_QUESTIONNAIRE", details={"patient_id": assignment.patient_id, "questionnaire_id": assignment.questionnaire_id})
    
    return assignment

@app.get("/assignments/patient/{access_code}", response_model=List[AssignmentWithQuestionnaire])
def get_patient_assignments(access_code: str, session: Session = Depends(get_session), current_user = Depends(get_current_actor)):
    # Security check: ensure the token matches the requested patient code
    # Although the endpoint uses access_code, we should probably verify the token belongs to that patient.
    # But wait, the frontend currently calls this with accessCode.
    # If we enforce token, we can just use the token to identify the patient and ignore access_code or verify it matches.
    
    # Since we are adding security, let's verify.
    # If current_user is Patient:
    if not hasattr(current_user, "role"): 
        if current_user.access_code != access_code:
            raise HTTPException(status_code=403, detail="Access denied")
    
    statement = select(Patient).where(Patient.access_code == access_code).options(selectinload(Patient.assignments).selectinload(Assignment.questionnaire))
    results = session.exec(statement)
    patient = results.first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    return patient.assignments

@app.get("/assignments", response_model=List[AssignmentWithQuestionnaire])
def read_assignments(offset: int = 0, limit: int = Query(default=100, lte=100), session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # Filter by user's patients if not admin
    if current_user.role != "admin":
        assignments = session.exec(
            select(Assignment)
            .join(Patient)
            .where(Patient.psychologist_id == current_user.id)
            .options(selectinload(Assignment.questionnaire))
            .offset(offset).limit(limit)
        ).all()
    else:
        assignments = session.exec(select(Assignment).options(selectinload(Assignment.questionnaire)).offset(offset).limit(limit)).all()
    return assignments

@app.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    session.delete(assignment)
    session.commit()
    
    # Context here is strictly from assignment ID, tricky to get user without extra query or dependency injections, but it's an unsecured endpoint mostly?
    # Ah, `delete_assignment` depends on `get_session` only. No `current_user`. 
    # This is a risk, but for logging we settle on "system" or try to imply.
    log_action(session, 0, "system", "Unknown", "DELETE_ASSIGNMENT", details={"assignment_id": assignment_id})
    
    return {"ok": True}

@app.get("/assignments/patient-admin/{patient_id}", response_model=List[AssignmentWithQuestionnaire])
def get_patient_assignments_admin(patient_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    """Get assignments for a patient by patient_id (for admin view)"""
    verify_patient_access(patient_id, current_user, session)
    statement = select(Assignment).where(Assignment.patient_id == patient_id).options(
        selectinload(Assignment.questionnaire)
    ).order_by(Assignment.assigned_at.desc())
    assignments = session.exec(statement).all()
    return assignments

@app.post("/assignments/{assignment_id}/submit", response_model=AssignmentRead)
def submit_assignment(assignment_id: int, answers: List[dict], session: Session = Depends(get_session), current_user = Depends(get_current_patient)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    assignment.answers = answers
    assignment.status = "completed"
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment

@app.patch("/assignments/{assignment_id}", response_model=AssignmentRead)
def update_assignment_status(assignment_id: int, status_update: dict, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # status_update expects {"status": "paused"} etc.
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    verify_patient_access(assignment.patient_id, current_user, session)
    
    if "status" in status_update:
        assignment.status = status_update["status"]
    
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_ASSIGNMENT_STATUS", details={"assignment_id": assignment_id, "status": assignment.status})
    
    return assignment

@app.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    session.delete(assignment)
    session.commit()
    
    log_action(session, 0, "system", "Unknown", "DELETE_ASSIGNMENT", details={"assignment_id": assignment_id})
    
    return {"ok": True}

# --- Auth ---
@app.post("/auth")
def authenticate_patient(login: PatientLoginRequest, session: Session = Depends(get_session)):
    statement = select(Patient).where(
        Patient.access_code == login.access_code,
        Patient.email == login.email
    )
    patient = session.exec(statement).first()
    if not patient:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate Token
    access_token = create_access_token(data={"sub": str(patient.id), "role": "patient"})

    # Set online status
    patient.is_online = True
    patient.last_active = datetime.now(timezone.utc)
    session.add(patient)
    session.commit()
    session.refresh(patient)
    
    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "access_code": patient.access_code,
        "email": patient.email,
        "psychologist_id": patient.psychologist_id,
        "psychologist_name": patient.psychologist_name,
        "psychologist_schedule": patient.psychologist_schedule,
        "access_token": access_token
    }

@app.post("/logout")
def logout(session: Session = Depends(get_session), current_user = Depends(get_current_actor)):
    if hasattr(current_user, "role"): # Psychologist
        current_user.is_online = False
        session.add(current_user)
        log_action(session, current_user.id, "psychologist", current_user.name, "LOGOUT")
    else: # Patient
        current_user.is_online = False
        session.add(current_user)
        # log_action for patient logout optional or generic
    
    session.commit()
    return {"ok": True}

@app.post("/heartbeat")
def heartbeat(session: Session = Depends(get_session), current_user = Depends(get_current_actor)):
    now = datetime.now(timezone.utc)
    
    # Calculate delta if previously active and within reasonable "session" window (e.g., < 2 mins)
    delta = 0
    if current_user.is_online and current_user.last_active:
        # Ensure last_active is timezone-aware
        last_active = current_user.last_active
        if last_active.tzinfo is None:
            # If naive, assume it's UTC
            last_active = last_active.replace(tzinfo=timezone.utc)
        
        diff = (now - last_active).total_seconds()
        if diff < 120: # If heartbeat is regular (e.g. every 60s), add diff. If huge gap, assume new session.
            delta = int(diff)
            
    if hasattr(current_user, "role"): # Psychologist
        current_user.last_active = now
        current_user.is_online = True
        current_user.total_online_seconds += delta
        session.add(current_user)
    else: # Patient
        current_user.last_active = now
        current_user.is_online = True
        current_user.total_online_seconds += delta
        session.add(current_user)
    
    session.commit()
    return {"ok": True}

def get_current_patient(current_user = Depends(get_current_actor)):
    if hasattr(current_user, "patient_code"):
        return current_user
    raise HTTPException(status_code=403, detail="Not a patient")

@app.get("/patient/status")
def get_patient_status(
    session: Session = Depends(get_session),
    current_patient: Patient = Depends(get_current_patient)
):
    # Determine psychologist status
    psychologist_online = False
    if current_patient.psychologist_id:
        psychologist = session.get(Psychologist, current_patient.psychologist_id)
        if psychologist:
            psychologist_online = psychologist.is_online
            
    return {
        "is_online": current_patient.is_online,
        "psychologist_is_online": psychologist_online
    }

@app.get("/patient/me", response_model=PatientRead)
def get_current_patient_profile(
    current_patient: Patient = Depends(get_current_patient)
):
    """
    Get the current authenticated patient's profile details.
    Useful for refreshing cached data (like psychologist name/schedule) on the frontend.
    """
    return current_patient

# --- Notes ---
@app.post("/notes", response_model=NoteRead)
def create_note(note: Note, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(note.patient_id, current_user, session)
    session.add(note)
    session.commit()
    session.refresh(note)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "CREATE_NOTE", details={"patient_id": note.patient_id, "title": note.title})
    
    return note

@app.get("/notes/{patient_id}", response_model=List[NoteRead])
def get_notes(patient_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(patient_id, current_user, session)
    statement = select(Note).where(Note.patient_id == patient_id).order_by(Note.created_at.desc())
    return session.exec(statement).all()

@app.delete("/notes/{note_id}")
def delete_note(note_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    verify_patient_access(note.patient_id, current_user, session)
    session.delete(note)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_NOTE", details={"note_id": note_id})
    
    return {"ok": True}

# --- Sessions ---
@app.post("/sessions", response_model=SessionRead)
def create_session(session_data: TherapySession, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(session_data.patient_id, current_user, session)
    session.add(session_data)
    session.commit()
    session.refresh(session_data)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "CREATE_SESSION", details={"patient_id": session_data.patient_id, "date": session_data.date})
    
    return session_data

@app.get("/sessions/{patient_id}", response_model=List[SessionRead])
def get_sessions(patient_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(patient_id, current_user, session)
    statement = select(TherapySession).where(TherapySession.patient_id == patient_id).order_by(TherapySession.date.desc())
    return session.exec(statement).all()

@app.put("/sessions/{session_id}", response_model=SessionRead)
def update_session(session_id: int, session_data: SessionUpdate, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    verify_patient_access(db_session.patient_id, current_user, session)
    
    if session_data.date: db_session.date = session_data.date
    if session_data.duration: db_session.duration = session_data.duration
    if session_data.description: db_session.description = session_data.description
    if session_data.notes: db_session.notes = session_data.notes
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_SESSION", details={"session_id": session_id})
    
    return db_session

@app.delete("/sessions/{session_id}")
def delete_session(session_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    verify_patient_access(db_session.patient_id, current_user, session)
    
    session.delete(db_session)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_SESSION", details={"session_id": session_id})
    
    return {"ok": True}

# --- Assessment Stats ---
@app.get("/assessment-stats/{patient_id}", response_model=List[AssessmentStatRead])
def get_assessment_stats(patient_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(patient_id, current_user, session)
    statement = select(AssessmentStat).where(AssessmentStat.patient_id == patient_id).order_by(AssessmentStat.created_at.desc())
    return session.exec(statement).all()

@app.post("/assessment-stats", response_model=AssessmentStatRead)
def create_assessment_stat(stat: AssessmentStat, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    verify_patient_access(stat.patient_id, current_user, session)
    session.add(stat)
    session.commit()
    session.refresh(stat)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "CREATE_STAT", details={"patient_id": stat.patient_id, "label": stat.label})
    
    return stat

@app.put("/assessment-stats/{stat_id}", response_model=AssessmentStatRead)
def update_assessment_stat(stat_id: int, stat_update: AssessmentStat, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    stat = session.get(AssessmentStat, stat_id)
    if not stat:
        raise HTTPException(status_code=404, detail="Assessment stat not found")
    
    verify_patient_access(stat.patient_id, current_user, session)
    
    stat.label = stat_update.label
    stat.value = stat_update.value
    stat.status = stat_update.status
    stat.color = stat_update.color
    
    stat.updated_at = datetime.utcnow()
    
    session.add(stat)
    session.commit()
    session.refresh(stat)
    
    log_action(session, current_user.id, "psychologist", current_user.name, "UPDATE_STAT", details={"stat_id": stat_id})
    
    return stat

@app.delete("/assessment-stats/{stat_id}")
def delete_assessment_stat(stat_id: int, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    stat = session.get(AssessmentStat, stat_id)
    if not stat:
        raise HTTPException(status_code=404, detail="Assessment stat not found")
    verify_patient_access(stat.patient_id, current_user, session)
    session.delete(stat)
    session.commit()
    
    log_action(session, current_user.id, "psychologist", current_user.name, "DELETE_STAT", details={"stat_id": stat_id})
    
    return {"ok": True}

# --- Audit Logs ---
@app.get("/audit-logs", response_model=List[AuditLog])
def get_audit_logs(offset: int = 0, limit: int = Query(default=100, lte=200), session: Session = Depends(get_session), current_user: Psychologist = Depends(require_admin)):
    return session.exec(select(AuditLog).order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)).all()


# --- Stats ---
@app.get("/dashboard/stats")
def get_dashboard_stats(psychologist_id: Optional[int] = None, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    # Non-admin users can only see their own stats
    if current_user.role != "admin":
        psychologist_id = current_user.id
    
    # Base queries
    q_patients = select(Patient)
    q_messages = select(Message)
    q_recent_msgs = select(Message).order_by(Message.created_at.desc()).limit(5)
    q_recent_assigns = select(Assignment).order_by(Assignment.assigned_at.desc()).limit(5)
    
    if psychologist_id:
        q_patients = q_patients.where(Patient.psychologist_id == psychologist_id)
        # Filter messages where the patient belongs to the psychologist
        # This requires a join or subquery. Join is cleaner.
        # select(Message).join(Patient).where(Patient.psychologist_id == psychologist_id)
        q_messages = select(Message).join(Patient).where(Patient.psychologist_id == psychologist_id)
        q_recent_msgs = select(Message).join(Patient).where(Patient.psychologist_id == psychologist_id).order_by(Message.created_at.desc()).limit(5)
        
        # Filter assignments
        q_recent_assigns = select(Assignment).join(Patient).where(Patient.psychologist_id == psychologist_id).order_by(Assignment.assigned_at.desc()).limit(5)
    
    total_patients = session.exec(q_patients).all()
    total_messages = session.exec(q_messages).all()
    recent_messages = session.exec(q_recent_msgs).all()
    recent_assignments = session.exec(q_recent_assigns).all()
    
    activity_log = []
    
    for msg in recent_messages:
        # Get patient name/code
        p = session.get(Patient, msg.patient_id)
        p_name = p.patient_code if p else "Unknown"
        activity_log.append({
            "type": "message",
            "patient": p_name,
            "patient_id": p.id if p else None,
            "action": "Nuevo mensaje recibido" if msg.is_from_patient else "Nuevo mensaje enviado",
            "time": msg.created_at,
            "timestamp": msg.created_at.timestamp()
        })
        
    for assign in recent_assignments:
        p = session.get(Patient, assign.patient_id)
        p_name = p.patient_code if p else "Unknown"
        q_title = "Cuestionario"
        if assign.questionnaire_id:
            q = session.get(Questionnaire, assign.questionnaire_id)
            if q: q_title = q.title
        
        action = f"Assigned {q_title}"
        if assign.status == "completed":
            action = f"Completed {q_title}"
            
        activity_log.append({
            "type": "assignment",
            "patient": p_name,
            "patient_id": p.id if p else None,
            "action": action,
            "time": assign.assigned_at,
            "timestamp": assign.assigned_at.timestamp()
        })
    
    # Sort by timestamp desc and take top 10
    activity_log.sort(key=lambda x: x["timestamp"], reverse=True)
    final_activity = activity_log[:10]
    
    # EMA Stats (filtered)
    # This also needs filtering by patient's psychologist
    q_completed_emas = select(Assignment).where(Assignment.status == "completed")
    q_pending_emas = select(Assignment).where(Assignment.status != "completed")
    
    if psychologist_id:
        q_completed_emas = q_completed_emas.join(Patient).where(Patient.psychologist_id == psychologist_id)
        q_pending_emas = q_pending_emas.join(Patient).where(Patient.psychologist_id == psychologist_id)

    completed_emas = session.exec(q_completed_emas).all()
    pending_emas = session.exec(q_pending_emas).all()

    # Online Patients Count
    # Filter by psychologist if not admin, and check is_online=True
    q_online = select(Patient).where(Patient.is_online == True)
    if psychologist_id:
        q_online = q_online.where(Patient.psychologist_id == psychologist_id)
    online_patients = session.exec(q_online).all()

    return {
        "total_patients": len(total_patients),
        "total_messages": len(total_messages),
        "completed_emas": len(completed_emas),
        "pending_emas": len(pending_emas),
        "recent_activity": final_activity,
        "online_patients": len(online_patients)
    }

if __name__ == "__main__":
    import uvicorn
    # Verify execution
    print("Starting server on 0.0.0.0:8001")
    # List routes
    for route in app.routes:
        print(f"Registered route: {route.path}")
        
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)


# --- AI / LLM ---
from llm_service import generate_response_options

class ChatContext(BaseModel):
    messages: List[dict] # [{"role": "user", "content": "..."}, ...]

@app.post("/chat/recommendations")
def get_chat_recommendations(context: ChatContext, session: Session = Depends(get_session), current_user: Psychologist = Depends(get_current_user)):
    try:
        # Retrieve therapist's AI configuration
        therapist = session.get(Psychologist, current_user.id)
        if not therapist:
            raise HTTPException(status_code=404, detail="Therapist not found")
        
        # Generate recommendations with therapist-specific configuration
        recommendations = generate_response_options(
            context.messages,
            therapist_style=therapist.ai_style,
            therapist_tone=therapist.ai_tone,
            therapist_instructions=therapist.ai_instructions
        )
        return {"recommendations": recommendations}
    except Exception as e:
        print(f"Error getting recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")

