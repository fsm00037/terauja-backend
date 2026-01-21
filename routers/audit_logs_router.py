from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import AuditLog, Psychologist
from auth import require_admin

router = APIRouter()

@router.get("", response_model=List[AuditLog])
def get_audit_logs(
    offset: int = 0, 
    limit: int = Query(default=100, lte=200), 
    session: Session = Depends(get_session), 
    current_user: Psychologist = Depends(require_admin)
):
    return session.exec(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    ).all()