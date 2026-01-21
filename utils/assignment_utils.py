import random
from datetime import datetime, timedelta, time
from sqlmodel import Session
from models import Assignment

def calculate_next_scheduled_time(assignment: Assignment, last_questionnaire_sent_at: datetime = None):
    """
    Calculates the next random notification time.
    last_questionnaire_sent_at: The timestamp of the previous questionnaire. If None, it's the first one.
    """
    now = datetime.utcnow()
    buffer_now = now + timedelta(minutes=2) # Don't schedule in the very past
    
    # 1. Parse Window
    try:
        h_start, m_start = map(int, (assignment.window_start or "09:00").split(':'))
        h_end, m_end = map(int, (assignment.window_end or "21:00").split(':'))
    except:
        h_start, m_start, h_end, m_end = 9, 0, 21, 0
        
    start_time = time(h_start, m_start)
    end_time = time(h_end, m_end)
    
    # 2. Define the absolute earliest we can send based on the GAP
    if last_questionnaire_sent_at:
        min_gap = timedelta(hours=assignment.min_hours_between or 0)
        earliest_by_gap = last_questionnaire_sent_at + min_gap
    else:
        earliest_by_gap = now

    # 3. Search for the first available window
    for i in range(8):
        candidate_date = (now + timedelta(days=i)).date()
        window_start_dt = datetime.combine(candidate_date, start_time)
        window_end_dt = datetime.combine(candidate_date, end_time)
        
        actual_search_start = max(window_start_dt, buffer_now, earliest_by_gap)
        print(".................................................................")
        print("actual_search_start",actual_search_start)
        print("window_end_dt",window_end_dt)
        print("buffer_now",buffer_now)
        print("earliest_by_gap",earliest_by_gap)
        print(".................................................................")
        
        if actual_search_start < window_end_dt:
            seconds_avail = int((window_end_dt - actual_search_start).total_seconds())
            
            # If we have at least 5 minutes of window left
            if seconds_avail > 300:
                random_sec = random.randint(0, seconds_avail)
                return actual_search_start + timedelta(seconds=random_sec)
                
    return now + timedelta(days=1)

def check_and_update_assignment_expiry(assignment: Assignment, session: Session):
    if assignment.status == "active" and assignment.end_date:
        try:
            # Normalize end_date to end of that day
            end_dt = datetime.fromisoformat(assignment.end_date.replace("Z", ""))
            if end_dt.time() == time(0, 0):
                end_dt = datetime.combine(end_dt.date(), time(23, 59, 59))
                
            if datetime.utcnow() > end_dt:
                assignment.status = "completed"
                session.add(assignment)
                session.commit() # Ensure state is saved
                return True
        except (ValueError, TypeError):
            pass
    return False