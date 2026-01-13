from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from typing import List, Optional
import secrets
from contextlib import asynccontextmanager

from database import create_db_and_tables, get_session
from models import Patient, Questionnaire, Assignment, AssignmentWithQuestionnaire, PatientReadWithAssignments, Message, MessageCreate, MessageRead, Note, Psychologist, PsychologistUpdate, Session as TherapySession, SessionUpdate, AssessmentStat
from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: str

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
                email="admin@terauja.com",
                password="admin", # Change in production
                role="admin",
                schedule="Siempre Disponible"
            )
            session.add(super_admin)
            session.commit()
            print("Default Admin Created: admin@terauja.com / admin")
    
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
    if not user or user.password != creds.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"id": user.id, "name": user.name, "role": user.role, "email": user.email}

@app.get("/psychologists", response_model=List[Psychologist])
def get_psychologists(session: Session = Depends(get_session)):
    return session.exec(select(Psychologist)).all()

@app.post("/psychologists", response_model=Psychologist)
def create_psychologist(psychologist: Psychologist, session: Session = Depends(get_session)):
    # Generate random password
    raw_password = secrets.token_urlsafe(8)
    psychologist.password = raw_password # in real app, hash this!
    
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
    return psychologist

@app.delete("/psychologists/{user_id}")
def delete_psychologist(user_id: int, session: Session = Depends(get_session)):
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
    return {"ok": True}

@app.get("/profile/{user_id}", response_model=Psychologist)
def get_user_profile(user_id: int, session: Session = Depends(get_session)):
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/profile/{user_id}", response_model=Psychologist)
def update_user_profile(user_id: int, profile_data: PsychologistUpdate, session: Session = Depends(get_session)):
    user = session.get(Psychologist, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if profile_data.name: user.name = profile_data.name
    if profile_data.schedule: user.schedule = profile_data.schedule
    if profile_data.phone: user.phone = profile_data.phone
        
    session.add(user)
    
    # Propagate changes to assigned patients
    patients = session.exec(select(Patient).where(Patient.psychologist_id == user_id)).all()
    for p in patients:
        if profile_data.name: p.psychologist_name = profile_data.name
        if profile_data.schedule: p.psychologist_schedule = profile_data.schedule
        session.add(p)
        
    session.commit()
    session.refresh(user)
    return user

# --- Patients ---

@app.post("/patients", response_model=Patient)
def create_patient(patient: Patient, session: Session = Depends(get_session)):
    # DEBUG LOGGING
    with open("debug_log.txt", "a") as f:
        f.write(f"create_patient called. Payload: {patient}\n")
        f.write(f"psychologist_id in payload: {patient.psychologist_id}\n")

    if not patient.access_code:
        patient.access_code = generate_access_code()
    # patient_code is expected in the input
    
    # If psychologist_id is provided (e.g. from frontend), verify it exists
    if patient.psychologist_id:
        psych = session.get(Psychologist, patient.psychologist_id)
        if psych:
            patient.psychologist_name = psych.name
            patient.psychologist_schedule = psych.schedule
    else:
        # Fallback: Try to find a default psychologist (e.g. Admin) or leave empty logic later
        default_psych = session.exec(select(Psychologist)).first()
        if default_psych:
            patient.psychologist_id = default_psych.id
            patient.psychologist_name = default_psych.name
            patient.psychologist_schedule = default_psych.schedule
            with open("debug_log.txt", "a") as f:
                f.write(f"Fallback used. Assigned to: {default_psych.name} (ID: {default_psych.id})\n")

    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient

@app.get("/patients", response_model=List[PatientReadWithAssignments])
def read_patients(offset: int = 0, limit: int = Query(default=100, lte=100), psychologist_id: Optional[int] = None, session: Session = Depends(get_session)):
    query = select(Patient).options(selectinload(Patient.assignments).selectinload(Assignment.questionnaire))
    if psychologist_id:
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
def assign_patient(patient_id: int, req: AssignRequest, session: Session = Depends(get_session)):
    patient = session.get(Patient, patient_id)
    psychologist = session.get(Psychologist, req.psychologist_id)
    
    if not patient or not psychologist:
        raise HTTPException(status_code=404, detail="Patient or Psychologist not found")
        
    patient.psychologist_id = psychologist.id
    patient.psychologist_name = psychologist.name
    patient.psychologist_schedule = psychologist.schedule
    
    session.add(patient)
    session.commit()
    return {"ok": True}

@app.patch("/patients/{patient_id}/clinical-summary")
def update_clinical_summary(patient_id: int, summary_data: dict, session: Session = Depends(get_session)):
    patient = session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient.clinical_summary = summary_data.get("clinical_summary", "")
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return {"ok": True, "clinical_summary": patient.clinical_summary}

# --- Questionnaires ---

@app.post("/questionnaires", response_model=Questionnaire)
def create_questionnaire(questionnaire: Questionnaire, session: Session = Depends(get_session)):
    session.add(questionnaire)
    session.commit()
    session.refresh(questionnaire)
    return questionnaire

@app.get("/questionnaires", response_model=List[Questionnaire])
def read_questionnaires(offset: int = 0, limit: int = Query(default=100, lte=100), session: Session = Depends(get_session)):
    questionnaires = session.exec(select(Questionnaire).offset(offset).limit(limit)).all()
    return questionnaires

@app.delete("/questionnaires/{questionnaire_id}")
def delete_questionnaire(questionnaire_id: int, session: Session = Depends(get_session)):
    questionnaire = session.get(Questionnaire, questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    session.delete(questionnaire)
    session.commit()
    return {"ok": True}

# --- Messages ---
@app.post("/messages", response_model=MessageRead)
def create_message(message: MessageCreate, session: Session = Depends(get_session)):
    db_message = Message.from_orm(message)
    # If message is from psychologist (not patient), mark as read automatically or handle differently?
    # Logic implies is_from_patient=False means sent by psychologist. 
    # Usually messages FROM patient are unread for psychologist.
    
    session.add(db_message)
    session.commit()
    session.refresh(db_message)
    return db_message

@app.post("/messages/mark-read/{patient_id}")
def mark_messages_read(patient_id: int, session: Session = Depends(get_session)):
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
    return {"ok": True, "count": len(messages)}

@app.get("/messages/{patient_id}", response_model=List[MessageRead])
def get_messages(patient_id: int, session: Session = Depends(get_session)):
    statement = select(Message).where(Message.patient_id == patient_id).order_by(Message.created_at)
    return session.exec(statement).all()

@app.delete("/messages/{patient_id}")
def delete_messages(patient_id: int, session: Session = Depends(get_session)):
    statement = select(Message).where(Message.patient_id == patient_id)
    results = session.exec(statement)
    for message in results:
        session.delete(message)
    session.commit()
    return {"ok": True, "deleted": True}

@app.put("/questionnaires/{questionnaire_id}", response_model=Questionnaire)
def update_questionnaire(questionnaire_id: int, updated_q: Questionnaire, session: Session = Depends(get_session)):
    questionnaire = session.get(Questionnaire, questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    
    questionnaire.title = updated_q.title
    questionnaire.description = updated_q.description
    questionnaire.questions = updated_q.questions
    
    session.add(questionnaire)
    session.commit()
    session.refresh(questionnaire)
    return questionnaire

# --- Assignments ---
@app.post("/assignments", response_model=Assignment)
def assign_questionnaire(assignment: Assignment, session: Session = Depends(get_session)):
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
    return assignment

@app.get("/assignments/patient/{access_code}", response_model=List[AssignmentWithQuestionnaire])
def get_patient_assignments(access_code: str, session: Session = Depends(get_session)):
    statement = select(Patient).where(Patient.access_code == access_code).options(selectinload(Patient.assignments).selectinload(Assignment.questionnaire))
    results = session.exec(statement)
    patient = results.first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    return patient.assignments

@app.get("/assignments", response_model=List[AssignmentWithQuestionnaire])
def read_assignments(offset: int = 0, limit: int = Query(default=100, lte=100), session: Session = Depends(get_session)):
    assignments = session.exec(select(Assignment).options(selectinload(Assignment.questionnaire)).offset(offset).limit(limit)).all()
    return assignments

@app.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    session.delete(assignment)
    session.commit()
    return {"ok": True}

@app.get("/assignments/patient-admin/{patient_id}", response_model=List[AssignmentWithQuestionnaire])
def get_patient_assignments_admin(patient_id: int, session: Session = Depends(get_session)):
    """Get assignments for a patient by patient_id (for admin view)"""
    statement = select(Assignment).where(Assignment.patient_id == patient_id).options(
        selectinload(Assignment.questionnaire)
    ).order_by(Assignment.assigned_at.desc())
    assignments = session.exec(statement).all()
    return assignments

@app.post("/assignments/{assignment_id}/submit", response_model=Assignment)
def submit_assignment(assignment_id: int, answers: List[dict], session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    assignment.answers = answers
    assignment.status = "completed"
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment

@app.patch("/assignments/{assignment_id}", response_model=Assignment)
def update_assignment_status(assignment_id: int, status_update: dict, session: Session = Depends(get_session)):
    # status_update expects {"status": "paused"} etc.
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if "status" in status_update:
        assignment.status = status_update["status"]
    
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment

@app.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    session.delete(assignment)
    session.commit()
    return {"ok": True}

# --- Auth ---
@app.get("/auth/{access_code}", response_model=Patient)
def authenticate_patient(access_code: str, session: Session = Depends(get_session)):
    statement = select(Patient).where(Patient.access_code == access_code)
    patient = session.exec(statement).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Invalid access code")
    return patient

# --- Notes ---
@app.post("/notes", response_model=Note)
def create_note(note: Note, session: Session = Depends(get_session)):
    session.add(note)
    session.commit()
    session.refresh(note)
    return note

@app.get("/notes/{patient_id}", response_model=List[Note])
def get_notes(patient_id: int, session: Session = Depends(get_session)):
    statement = select(Note).where(Note.patient_id == patient_id).order_by(Note.created_at.desc())
    return session.exec(statement).all()

@app.delete("/notes/{note_id}")
def delete_note(note_id: int, session: Session = Depends(get_session)):
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    session.delete(note)
    session.commit()
    return {"ok": True}

# --- Sessions ---
@app.post("/sessions", response_model=TherapySession)
def create_session(session_data: TherapySession, session: Session = Depends(get_session)):
    try:
        print(f"DEBUG: create_session called with {session_data}")
        # Log to file
        with open("debug_log.txt", "a") as f:
            f.write(f"create_session called with {session_data}\\n")
            
        session.add(session_data)
        session.commit()
        session.refresh(session_data)
        return session_data
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"ERROR in create_session: {error_msg}")
        with open("debug_log.txt", "a") as f:
            f.write(f"ERROR in create_session: {error_msg}\\n")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/sessions/{patient_id}", response_model=List[TherapySession])
def get_sessions(patient_id: int, session: Session = Depends(get_session)):
    statement = select(TherapySession).where(TherapySession.patient_id == patient_id).order_by(TherapySession.date.desc())
    return session.exec(statement).all()

@app.put("/sessions/{session_id}", response_model=TherapySession)
def update_session(session_id: int, session_data: SessionUpdate, session: Session = Depends(get_session)):
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session_data.date: db_session.date = session_data.date
    if session_data.duration: db_session.duration = session_data.duration
    if session_data.description: db_session.description = session_data.description
    if session_data.notes: db_session.notes = session_data.notes
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    return db_session

@app.delete("/sessions/{session_id}")
def delete_session(session_id: int, session: Session = Depends(get_session)):
    db_session = session.get(TherapySession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.delete(db_session)
    session.commit()
    return {"ok": True}

# --- Assessment Stats ---
@app.get("/assessment-stats/{patient_id}", response_model=List[AssessmentStat])
def get_assessment_stats(patient_id: int, session: Session = Depends(get_session)):
    statement = select(AssessmentStat).where(AssessmentStat.patient_id == patient_id).order_by(AssessmentStat.created_at.desc())
    return session.exec(statement).all()

@app.post("/assessment-stats", response_model=AssessmentStat)
def create_assessment_stat(stat: AssessmentStat, session: Session = Depends(get_session)):
    session.add(stat)
    session.commit()
    session.refresh(stat)
    return stat

@app.put("/assessment-stats/{stat_id}", response_model=AssessmentStat)
def update_assessment_stat(stat_id: int, stat_update: AssessmentStat, session: Session = Depends(get_session)):
    stat = session.get(AssessmentStat, stat_id)
    if not stat:
        raise HTTPException(status_code=404, detail="Assessment stat not found")
    
    stat.label = stat_update.label
    stat.value = stat_update.value
    stat.status = stat_update.status
    stat.color = stat_update.color
    from datetime import datetime
    stat.updated_at = datetime.utcnow()
    
    session.add(stat)
    session.commit()
    session.refresh(stat)
    return stat

@app.delete("/assessment-stats/{stat_id}")
def delete_assessment_stat(stat_id: int, session: Session = Depends(get_session)):
    stat = session.get(AssessmentStat, stat_id)
    if not stat:
        raise HTTPException(status_code=404, detail="Assessment stat not found")
    session.delete(stat)
    session.commit()
    return {"ok": True}

# --- Stats ---
@app.get("/dashboard/stats")
def get_dashboard_stats(psychologist_id: Optional[int] = None, session: Session = Depends(get_session)):
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
            "action": "New message received" if msg.is_from_patient else "Message sent",
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

    return {
        "total_patients": len(total_patients),
        "total_messages": len(total_messages),
        "completed_emas": len(completed_emas),
        "pending_emas": len(pending_emas),
        "recent_activity": final_activity
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
def get_chat_recommendations(context: ChatContext, session: Session = Depends(get_session)):
    try:
        # Check if llm_service is configured (optional check)
        # Assuming generate_response_options handles errors gracefully
        recommendations = generate_response_options(context.messages)
        return {"recommendations": recommendations}
    except Exception as e:
        print(f"Error getting recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")

