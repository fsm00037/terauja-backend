from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from dotenv import load_dotenv
import os
import asyncio
from services.scheduler import run_scheduler

load_dotenv()

from database import create_db_and_tables, engine
from models import Psychologist, Questionnaire
from auth import hash_password

from routers import (
    auth_router,
    psychologists_router,
    patients_router,
    questionnaires_router,
    assignments_router,
    messages_router,
    notes_router,
    sessions_router,
    assessment_stats_router,
    audit_logs_router,
    dashboard_router,
    dashboard_router,
    chat_router,
    superadmin_router,
    notifications_router
)
from services.firebase_service import initialize_firebase

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    
    # Create Default Super Admin if no users exist
    with Session(engine) as session:
        admin = session.exec(select(Psychologist).where(Psychologist.role == "admin")).first()
        if not admin:
            super_admin = Psychologist(
                name="Admin",
                email="admin@psicouja.com",
                password=hash_password("admin"),
                role="admin",
                schedule="Siempre Disponible"
            )
            session.add(super_admin)
            session.commit()
    
        # Create Default EMA Questionnaire if it doesn't exist
        ema = session.exec(select(Questionnaire).where(Questionnaire.title == "EMA")).first()
        if not ema:
            ema_q = Questionnaire(
                title="EMA",
                icon="Activity",
                description="Evaluación Ecológica Momentánea diaria",
                questions=[
                    {"id": "1", "text": "A continuación encontrarás una serie de preguntas sobre cómo te has sentido y cómo has actuado en las últimas dos horas. Lee cada pregunta con atención y marca el número que mejor describa tu experiencia. No hay respuestas correctas o incorrectas.\nEn las últimas dos horas, ¿has sentido poco interés o placer en hacer las cosas?", "type": "likert", "min": 1, "max": 7, "minLabel": "Nada", "maxLabel": "Todo el tiempo"},
                    {"id": "2", "text": "En las últimas dos horas, ¿te has sentido desanimado, deprimido o desesperanzado?", "type": "likert", "min": 1, "max": 7, "minLabel": "Nada", "maxLabel": "Todo el tiempo"},
                    {"id": "3", "text": "En las últimas dos horas, ¿te has sentido nervioso, ansioso o con los nervios de punta?", "type": "likert", "min": 1, "max": 7, "minLabel": "Nada", "maxLabel": "Todo el tiempo"},
                    {"id": "4", "text": "En las últimas dos horas, ¿has sentido que no podías parar de preocuparte?", "type": "likert", "min": 1, "max": 7, "minLabel": "Nada", "maxLabel": "Todo el tiempo"},
                    {"id": "5", "text": "En las dos últimas horas, ¿has evitado hacer algo que pudiera traerte pensamientos o sentimientos difíciles?", "type": "likert", "min": 1, "max": 7, "minLabel": "Nada", "maxLabel": "Todo el tiempo"},
                    {"id": "6", "text": "En las últimas dos horas, ¿has sentido que ibas en “piloto automático” sin prestar atención a lo que hacías?", "type": "likert", "min": 1, "max": 7, "minLabel": "Nada", "maxLabel": "Todo el tiempo"},
                    {"id": "7", "text": "En las últimas dos horas, ¿has actuado de forma consistente con cómo deseas vivir tu vida?", "type": "likert", "min": 1, "max": 7, "minLabel": "Nada consistente", "maxLabel": "Totalmente consistente"}
                ]
            )
            session.add(ema_q)
            session.commit()
    
    # Initialize Firebase
    initialize_firebase()
    
    # Start Background Scheduler
    asyncio.create_task(run_scheduler())
    
    yield

app = FastAPI(lifespan=lifespan)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(auth_router.router, tags=["Authentication"])
app.include_router(psychologists_router.router, tags=["Psychologists"])
app.include_router(patients_router.router, tags=["Patients"])
app.include_router(questionnaires_router.router, prefix="/questionnaires", tags=["Questionnaires"])
app.include_router(assignments_router.router, prefix="/assignments", tags=["Assignments"])
app.include_router(messages_router.router, prefix="/messages", tags=["Messages"])
app.include_router(notes_router.router, prefix="/notes", tags=["Notes"])
app.include_router(sessions_router.router, prefix="/sessions", tags=["Sessions"])
app.include_router(assessment_stats_router.router, prefix="/assessment-stats", tags=["Assessment Stats"])
app.include_router(audit_logs_router.router, prefix="/audit-logs", tags=["Audit Logs"])
app.include_router(dashboard_router.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(chat_router.router, prefix="/chat", tags=["Chat AI"])
app.include_router(superadmin_router.router, prefix="/superadmin", tags=["Superadmin"])
app.include_router(notifications_router.router, prefix="/notifications", tags=["Notifications"])

@app.get("/")
def read_root():
    return {"message": "Psychology Backend API is running"}

if __name__ == "__main__":
    import uvicorn
    for route in app.routes:
        print(f"Registered route: {route.path}")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)