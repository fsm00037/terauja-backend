from sqlmodel import Session
from models import AuditLog
import json
from utils.logger import logger

def log_action(
    session: Session,
    actor_id: int,
    actor_type: str,
    actor_name: str,
    action: str,
    details: dict | str = None,
    ip_address: str = None
):
    """
    Logs a user action to the AuditLog table and the centralized logger.
    """
    try:
        details_str = ""
        if isinstance(details, dict):
            details_str = json.dumps(details, default=str)
        elif details:
            details_str = str(details)
            
        log_entry = AuditLog(
            actor_id=actor_id,
            actor_type=actor_type,
            actor_name=actor_name,
            action=action,
            details=details_str,
            ip_address=ip_address
        )
        session.add(log_entry)
        session.commit()
        
        # Log to centralized logger instead of print/manual file
        log_msg = f"{action} | {actor_type.upper()}: {actor_name} (ID:{actor_id})"
        if details_str:
            log_msg += f" | Details: {details_str}"
        if ip_address:
            log_msg += f" | IP: {ip_address}"
            
        logger.success(f"Audit: {log_msg}")
            
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
