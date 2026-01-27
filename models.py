from typing import List, Optional, Dict, Any
from sqlmodel import Field, SQLModel, Relationship, JSON, Column
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.mutable import MutableList
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

    @property
    def is_active_now(self) -> bool:
        if not self.is_online or not self.last_active:
            return False
        
        # Usamos un margen de 2 minutos (120 segundos)
        now = datetime.now(timezone.utc)
        last_active_utc = self.last_active
        if last_active_utc.tzinfo is None:
            last_active_utc = last_active_utc.replace(tzinfo=timezone.utc)
            
        return (now - last_active_utc) < timedelta(seconds=120)


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
    questionnaire_completions: List["QuestionnaireCompletion"] = Relationship(back_populates="patient")

    @property
    def is_active_now(self) -> bool:
        if not self.is_online or not self.last_active:
            return False
        
        # Usamos un margen de 2 minutos (120 segundos)
        now = datetime.now(timezone.utc)
        last_active_utc = self.last_active
        if last_active_utc.tzinfo is None:
            last_active_utc = last_active_utc.replace(tzinfo=timezone.utc)
            
        return (now - last_active_utc) < timedelta(seconds=120)


class PatientRead(SQLModel):
    id: int
    patient_code: str
    access_code: str
    name: str = Field(default="Paciente")
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
    is_online: bool = False
    total_online_seconds: int = 0
    last_active: Optional[datetime] = None
    created_at: datetime
    psychologist_id: Optional[int] = None
    psychologist_name: Optional[str] = None
    psychologist_photo: Optional[str] = None
    clinical_summary: Optional[str] = None
    unread_messages: int = 0
    unread_questionnaires: int = 0
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
    status: str = Field(default="active") 
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
    min_hours_between: Optional[int] = Field(default=8)
    next_scheduled_at: Optional[datetime] = Field(default=None)

    patient: "Patient" = Relationship(back_populates="assignments")
    questionnaire: "Questionnaire" = Relationship(back_populates="assignments")


class QuestionnaireCompletion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    assignment_id: int = Field(foreign_key="assignment.id")
    patient_id: int = Field(foreign_key="patient.id")
    questionnaire_id: int = Field(foreign_key="questionnaire.id")
    answers: Optional[List[Dict]] = Field(default=None, sa_column=Column(JSON))
    scheduled_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="pending") # pending, completed, missed
    is_delayed: bool = Field(default=False)
    read_by_therapist: bool = Field(default=False)

    patient: "Patient" = Relationship(back_populates="questionnaire_completions")
    assignment: "Assignment" = Relationship()
    questionnaire: "Questionnaire" = Relationship()


class AssignmentRead(SQLModel):
    id: int
    patient_id: int
    questionnaire_id: int
    status: str
    answers: Optional[List[Dict]] = None
    assigned_at: datetime
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    next_scheduled_at: Optional[datetime] = None
    questionnaire: Optional["QuestionnaireRead"] = None
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
    psychologist_id: Optional[int] = Field(default=None, foreign_key="psychologist.id")
    date: datetime = Field(default_factory=datetime.utcnow)
    duration: str = "0 min"
    description: str = ""
    notes: str = ""
    chat_snapshot: Optional[List[Dict[str, Any]]] = Field(
        default=None, 
        sa_column=Column(MutableList.as_mutable(JSON)) 
    )
    # Privacy field
    patient: Patient = Relationship(back_populates="sessions")


class SessionRead(SQLModel):
    id: int
    patient_id: int
    date: datetime
    duration: str
    description: str
    notes: str
    chat_snapshot: Optional[List[Dict[str, Any]]] = Field(
        default=None, 
        sa_column=Column(MutableList.as_mutable(JSON)) 
    )


class SessionUpdate(SQLModel):
    date: Optional[datetime] = None
    duration: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    chat_snapshot: Optional[List[Dict[str, Any]]] = Field(
        default=None, 
        sa_column=Column(MutableList.as_mutable(JSON)) 
    )


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
    
    # Privacy field
    psychologist_id: Optional[int] = Field(default=None, foreign_key="psychologist.id")


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
    psychologist_id: Optional[int] = Field(default=None, foreign_key="psychologist.id")
    content: str
    is_from_patient: bool = True
    read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    used_ai_suggestion: bool = Field(default=False)
    was_edited_by_human: bool = Field(default=False)
    ai_suggestion_log_id: Optional[int] = Field(default=None, foreign_key="aisuggestionlog.id")

class MessageRead(SQLModel):
    id: int
    patient_id: int
    content: str
    is_from_patient: bool
    read: bool
    created_at: datetime
    was_edited_by_human: bool = False
    ai_suggestion_log_id: Optional[int] = None

class MessageCreate(SQLModel):
    patient_id: int
    content: str
    is_from_patient: bool = True
    ai_suggestion_log_id: Optional[int] = None
    selected_option: Optional[int] = None # 1, 2, 3 or None
    was_edited_by_human: bool = False

    
# ============================================================================
# AISUGGESTION LOG MODELS
# ============================================================================

class AISuggestionLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    psychologist_id: int = Field(foreign_key="psychologist.id")
    
    # El contexto de la IA en ese momento (Snapshot)
    ai_style_used: Optional[str] = None
    ai_tone_used: Optional[str] = None
    ai_instructions_used: Optional[str] = None
    
    # Las 3 sugerencias 
    suggestion_model1: str
    suggestion_model2: str
    suggestion_model3: str
    
    raw_options: Optional[str] = None

    # Metadatos
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Cual de las 3 opciones ha clickado el terapeuta
    final_option_id: Optional[int] = Field(default=None)

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
# ============================================================================
# PUSH SUBSCRIPTION MODELS
# ============================================================================

class PushSubscription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    endpoint: str = Field(index=True)
    p256dh: str
    auth: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
