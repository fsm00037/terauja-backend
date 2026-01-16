from typing import List, Optional, Dict
from sqlmodel import Field, SQLModel, Relationship, JSON, Column
from datetime import datetime


# ============================================================================
# PSYCHOLOGIST MODELS
# ============================================================================

class Psychologist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="Tu Psicólogo")
    email: str = Field(unique=True, index=True)
    password: str  # Hashed or plain for demo
    role: str = Field(default="psychologist")  # "admin" (super) or "psychologist"
    schedule: str = Field(default="Lunes a Viernes, 9:00 - 18:00")
    phone: Optional[str] = None
    is_online: bool = Field(default=False)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    total_online_seconds: int = Field(default=0)
    photo_url: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # AI Configuration
    ai_style: Optional[str] = Field(default=None)
    ai_tone: Optional[str] = Field(default=None)
    ai_instructions: Optional[str] = Field(default=None)
    
    patients: List["Patient"] = Relationship(back_populates="psychologist")


class PsychologistRead(SQLModel):
    id: int
    name: str
    email: str
    role: str
    schedule: str
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    is_online: bool = False
    total_online_seconds: int = 0
    last_active: datetime
    created_at: datetime
    ai_style: Optional[str] = None
    ai_tone: Optional[str] = None
    ai_instructions: Optional[str] = None


class PsychologistUpdate(SQLModel):
    name: Optional[str] = None
    email: Optional[str] = None
    schedule: Optional[str] = None
    phone: Optional[str] = None
    ai_style: Optional[str] = None
    ai_tone: Optional[str] = None
    ai_instructions: Optional[str] = None


# ============================================================================
# PATIENT MODELS
# ============================================================================

class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_code: str = Field(unique=True, index=True)  # Public Identifier
    access_code: str = Field(unique=True, index=True)  # Private Login Token
    email: Optional[str] = None
    is_online: bool = Field(default=False)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    total_online_seconds: int = Field(default=0)
    
    # Link to specific psychologist
    psychologist_id: Optional[int] = Field(default=None, foreign_key="psychologist.id")
    psychologist: Optional[Psychologist] = Relationship(back_populates="patients")

    # Snapshot fields
    psychologist_name: str = Field(default="Tu Psicólogo") 
    psychologist_schedule: str = Field(default="Lunes a Viernes, 9:00 - 18:00")
    psychologist_photo: Optional[str] = Field(default=None)
    
    # Clinical summary / case description
    clinical_summary: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

    assignments: List["Assignment"] = Relationship(back_populates="patient")
    sessions: List["Session"] = Relationship(back_populates="patient")


class PatientRead(SQLModel):
    id: int
    patient_code: str
    access_code: str
    email: Optional[str] = None
    is_online: bool = False
    total_online_seconds: int = 0
    last_active: datetime
    psychologist_id: Optional[int] = None
    psychologist_name: Optional[str] = None
    psychologist_schedule: Optional[str] = None
    psychologist_photo: Optional[str] = None
    clinical_summary: Optional[str] = None
    created_at: datetime


class PatientReadWithAssignments(SQLModel):
    id: int
    patient_code: str
    access_code: str
    email: Optional[str] = None
    is_online: bool = False
    total_online_seconds: int = 0
    last_active: Optional[datetime] = None
    created_at: datetime
    psychologist_id: Optional[int] = None
    psychologist_name: Optional[str] = None
    psychologist_photo: Optional[str] = None
    clinical_summary: Optional[str] = None
    unread_messages: int = 0
    assignments: List["AssignmentWithQuestionnaire"] = []


# ============================================================================
# QUESTIONNAIRE MODELS
# ============================================================================

class Questionnaire(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    icon: str = "FileQuestion"
    description: Optional[str] = None
    questions: List[Dict] = Field(default=[], sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    assignments: List["Assignment"] = Relationship(back_populates="questionnaire")


class QuestionnaireRead(SQLModel):
    id: int
    title: str
    icon: str
    description: Optional[str] = None
    questions: List[Dict] = []
    created_at: datetime


# ============================================================================
# ASSIGNMENT MODELS
# ============================================================================

class Assignment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    questionnaire_id: int = Field(foreign_key="questionnaire.id")
    status: str = Field(default="active")  # active, paused, completed
    answers: Optional[List[Dict]] = Field(default=None, sa_column=Column(JSON))
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Scheduling Fields
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    frequency_type: Optional[str] = "weekly"
    frequency_count: Optional[int] = 1
    window_start: Optional[str] = "09:00"
    window_end: Optional[str] = "21:00"
    deadline_hours: Optional[int] = 2

    patient: Patient = Relationship(back_populates="assignments")
    questionnaire: Questionnaire = Relationship(back_populates="assignments")


class AssignmentRead(SQLModel):
    id: int
    patient_id: int
    questionnaire_id: int
    status: str
    answers: Optional[List[Dict]] = None
    assigned_at: datetime
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    frequency_type: Optional[str] = None
    frequency_count: Optional[int] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    deadline_hours: Optional[int] = None


class AssignmentWithQuestionnaire(AssignmentRead):
    questionnaire: QuestionnaireRead


# ============================================================================
# SESSION MODELS
# ============================================================================

class Session(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    date: datetime = Field(default_factory=datetime.utcnow)
    duration: str = "0 min"
    description: str = ""
    notes: str = ""
    chat_snapshot: Optional[List[Dict]] = Field(default=None, sa_column=Column(JSON))

    patient: Patient = Relationship(back_populates="sessions")


class SessionRead(SQLModel):
    id: int
    patient_id: int
    date: datetime
    duration: str
    description: str
    notes: str
    chat_snapshot: Optional[List[Dict]] = None


class SessionUpdate(SQLModel):
    date: Optional[datetime] = None
    duration: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# ASSESSMENT STATS MODELS
# ============================================================================

class AssessmentStat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    label: str  # e.g., "PHQ-9", "GAD-7"
    value: str  # e.g., "12/27"
    status: str = "mild"  # mild, moderate, high, severe
    color: str = "teal"  # teal, amber, coral
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AssessmentStatRead(SQLModel):
    id: int
    patient_id: int
    label: str
    value: str
    status: str
    color: str
    created_at: datetime
    updated_at: datetime


# ============================================================================
# NOTE MODELS
# ============================================================================

class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    title: str
    content: str
    color: str = "bg-white"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NoteRead(SQLModel):
    id: int
    patient_id: int
    title: str
    content: str
    color: str
    created_at: datetime


# ============================================================================
# MESSAGE MODELS
# ============================================================================

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    content: str
    is_from_patient: bool = True
    read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MessageRead(SQLModel):
    id: int
    patient_id: int
    content: str
    is_from_patient: bool
    read: bool
    created_at: datetime


class MessageCreate(SQLModel):
    patient_id: int
    content: str
    is_from_patient: bool = True


# ============================================================================
# AUDIT LOG MODELS
# ============================================================================

class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: Optional[int] = None  # Can be Psychologist ID or Patient ID
    actor_type: str  # "psychologist", "patient", "system"
    actor_name: str  # Snapshot of name at time of action
    action: str  # LOGIN, CREATE, UPDATE, DELETE, etc.
    details: Optional[str] = None  # JSON string or text details
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)