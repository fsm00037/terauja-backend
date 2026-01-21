from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from dotenv import load_dotenv
import os

load_dotenv()

from database import create_db_and_tables, engine
from models import Psychologist
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
    chat_router
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    
    # Create Default Super Admin if no users exist
    with Session(engine) as session:
        admin = session.exec(select(Psychologist).where(Psychologist.role == "admin")).first()
        if not admin:
            print("Creating default Super Admin...")
            super_admin = Psychologist(
                name="Super Admin",
                email="admin@psicouja.com",
                password=hash_password("admin"),
                role="admin",
                schedule="Siempre Disponible"
            )
            session.add(super_admin)
            session.commit()
            print("Default Admin Created: admin@psicouja.com / admin")
    
    yield

app = FastAPI(lifespan=lifespan)

# CORS Configuration
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

@app.get("/")
def read_root():
    return {"message": "Psychology Backend API is running"}

if __name__ == "__main__":
    import uvicorn
    print("Starting server on 0.0.0.0:8001")
    for route in app.routes:
        print(f"Registered route: {route.path}")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)