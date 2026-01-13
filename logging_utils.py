from sqlmodel import Session
from models import AuditLog
import json

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
    Logs a user action to the AuditLog table.
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
        
        # Also write to file
        log_line = f"[{log_entry.timestamp}] {actor_type.upper()} ({actor_name} ID:{actor_id}) - {action}: {details_str}"
        if ip_address:
            log_line += f" [IP: {ip_address}]"
        
        with open("audit.log", "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
            
    except Exception as e:
        print(f"Failed to write audit log: {e}")
