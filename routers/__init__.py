"""
Routers package for the Psychology Backend API.
This module exports all the routers for easy importing in main.py
"""

from . import (
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
    chat_router,
    notifications_router
)

__all__ = [
    "auth_router",
    "psychologists_router",
    "patients_router",
    "questionnaires_router",
    "assignments_router",
    "messages_router",
    "notes_router",
    "sessions_router",
    "assessment_stats_router",
    "audit_logs_router",
    "dashboard_router",
    "chat_router",
    "notifications_router"
]