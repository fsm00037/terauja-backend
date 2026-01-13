from typing import List, Optional, Dict
from sqlmodel import Field, SQLModel, Relationship, JSON
from datetime import datetime

class Psychologist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="Tu Psicólogo")
    email: str = Field(unique=True, index=True)
    password: str # Hashed or plain for demo
    role: str = Field(default="psychologist") # "admin" (super) or "psychologist"
    schedule: str = Field(default="Lunes a Viernes, 9:00 - 18:00")
    phone: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    patients: List["Patient"] = Relationship(back_populates="psychologist")

class PsychologistUpdate(SQLModel):
    name: Optional[str] = None
    email: Optional[str] = None
    schedule: Optional[str] = None
    phone: Optional[str] = None

class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_code: str = Field(unique=True, index=True) # Public Identifier
    access_code: str = Field(unique=True, index=True) # Private Login Token
    
    # Link to specific psychologist
    psychologist_id: Optional[int] = Field(default=None, foreign_key="psychologist.id")
    psychologist: Optional[Psychologist] = Relationship(back_populates="patients")

    # Snapshot fields (in case psychologist is deleted or changed, though relation is better)
    # Keeping these for backward compatibility or direct access if needed, 
    # but ideally we pull from relationship.
    psychologist_name: str = Field(default="Tu Psicólogo") 
    psychologist_schedule: str = Field(default="Lunes a Viernes, 9:00 - 18:00")
    
    # Clinical summary / case description
    clinical_summary: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

    assignments: List["Assignment"] = Relationship(back_populates="patient")
    sessions: List["Session"] = Relationship(back_populates="patient")

class Questionnaire(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    icon: str = "FileQuestion"
    description: Optional[str] = None
    questions: List[Dict] = Field(default=[], sa_type=JSON)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    assignments: List["Assignment"] = Relationship(back_populates="questionnaire")

class Assignment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    questionnaire_id: int = Field(foreign_key="questionnaire.id")
    status: str = Field(default="active") # active, paused, completed
    answers: Optional[List[Dict]] = Field(default=None, sa_type=JSON)
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

class QuestionnaireRead(SQLModel):
    id: int
    title: str
    icon: str
    description: Optional[str] = None
    questions: List[Dict] = []
    created_at: datetime

class AssignmentRead(SQLModel):
    id: int
    patient_id: int
    questionnaire_id: int
    status: str
    answers: Optional[List[Dict]] = None
    assigned_at: datetime
    start_date: Optional[str]
    end_date: Optional[str]
    frequency_type: Optional[str]
    frequency_count: Optional[int]
    window_start: Optional[str]
    window_end: Optional[str]
    deadline_hours: Optional[int]

class AssignmentWithQuestionnaire(AssignmentRead):
    questionnaire: QuestionnaireRead

class Session(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    date: datetime = Field(default_factory=datetime.utcnow)
    duration: str = "0 min"
    description: str = ""
    notes: str = ""
    
    # Store chat history as JSON snapshot if needed, or link to messages?
    # Requirement says "chat notes" and "sessions".
    # Linking to messages by time range is complex.
    # Storing a snapshot of relevant chat IDs or text might be easier for "Chat History" within a session.
    # For now, let's store a simple JSON or string for chat summary/snapshot if the user wants "Chat History" preserved *as part of the session*.
    # Actually, the frontend shows "chatHistory" as an array of messages.
    # Let's add a JSON field for this snapshot.
    chat_snapshot: Optional[List[Dict]] = Field(default=None, sa_type=JSON)

    patient: Patient = Relationship(back_populates="sessions")

class SessionUpdate(SQLModel):
    date: Optional[datetime] = None
    duration: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


class AssessmentStat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    label: str  # e.g., "PHQ-9", "GAD-7"
    value: str  # e.g., "12/27"
    status: str = "mild"  # mild, moderate, high, severe
    color: str = "teal"  # teal, amber, coral
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PatientReadWithAssignments(SQLModel):
    id: int
    patient_code: str
    access_code: str
    created_at: datetime
    psychologist_id: Optional[int] = None
    psychologist_name: Optional[str] = None
    clinical_summary: Optional[str] = None
    unread_messages: int = 0
    assignments: List[AssignmentWithQuestionnaire] = []
    # sessions: List[Session] = [] # We'll need a new read model or unrelated query

class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    title: str
    content: str
    color: str = "bg-white"
    created_at: datetime = Field(default_factory=datetime.utcnow)

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

class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: Optional[int] = None # Can be Psychologist ID or Patient ID
    actor_type: str # "psychologist", "patient", "system"
    actor_name: str # Snapshot of name at time of action
    action: str # LOGIN, CREATE, UPDATE, DELETE, etc.
    details: Optional[str] = None # JSON string or text details
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
