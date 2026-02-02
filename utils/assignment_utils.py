import random
from datetime import datetime, timedelta, time, timezone
from sqlmodel import Session, select, or_
from models import Assignment, QuestionnaireCompletion

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

def cleanup_previous_completions(session: Session, patient_id: int, questionnaire_id: int, exclude_completion_id: int = None):
    """
    Soft-deletes previous incomplete completions (pending, sent, missed) for a specific patient and questionnaire.
    This ensures that when a new questionnaire is essentially 'activated' (sent), old ones are cleared.
    """
    try:
        # Find existing completions that are not completed (pending, sent, missed)
        statement = (
            select(QuestionnaireCompletion)
            .where(QuestionnaireCompletion.patient_id == patient_id)
            .where(QuestionnaireCompletion.questionnaire_id == questionnaire_id)
            .where(or_(QuestionnaireCompletion.status == "pending", QuestionnaireCompletion.status == "sent", QuestionnaireCompletion.status == "missed"))
            .where(QuestionnaireCompletion.deleted_at == None)
        )
        
        existing_completions = session.exec(statement).all()
        
        now_utc = datetime.now(timezone.utc)
        count_deleted = 0
        affected_assignment_ids = set()
        
        for ec in existing_completions:
            # Skip the one we are currently processing (if any)
            if exclude_completion_id and ec.id == exclude_completion_id:
                continue
                
            ec.deleted_at = now_utc
            session.add(ec)
            affected_assignment_ids.add(ec.assignment_id)
            count_deleted += 1
            
        # Also clean up the parent assignments
        if affected_assignment_ids:
            assignments_to_delete = session.exec(
                select(Assignment).where(Assignment.id.in_(affected_assignment_ids))
            ).all()
            for old_assignment in assignments_to_delete:
                old_assignment.deleted_at = now_utc
                session.add(old_assignment)
            print(f"Cleanup: Also deleted {len(assignments_to_delete)} parent assignments.")
            
        print(f"Cleanup: Deleted {count_deleted} previous completions for patient {patient_id} questionnaire {questionnaire_id}")
            
    except Exception as e:
        print(f"Error in cleanup_previous_completions: {e}")

def generate_schedule_dates(start_date_str: str, end_date_str: str, frequency_type: str, count: int, window_start: str = "09:00", window_end: str = "21:00") -> list[datetime]:

    try:
        start_dt = datetime.fromisoformat(start_date_str)
        end_dt = datetime.fromisoformat(end_date_str)
        
        # Parse window times
        try:
            h_start, m_start = map(int, window_start.split(':'))
            h_end, m_end = map(int, window_end.split(':'))
        except:
            h_start, m_start = 9, 0
            h_end, m_end = 21, 0
            
        dates = []
        current = start_dt
        
        def get_random_time_for_date(base_date):
            # Create datetime objects for the window on this specific date
            start_window = datetime.combine(base_date.date(), time(h_start, m_start))
            end_window = datetime.combine(base_date.date(), time(h_end, m_end))
            
            # If end window is before start window (e.g. overnight), handle it? 
            # For simplicity assuming same day window.
            
            if start_window >= end_window:
                # Fallback to fixed time if window is invalid
                return start_window
            
            total_seconds = int((end_window - start_window).total_seconds())
            random_seconds = random.randint(0, total_seconds)
            return start_window + timedelta(seconds=random_seconds)

        if frequency_type == "daily":
            step = timedelta(days=1)
            while current <= end_dt:
                dates.append(get_random_time_for_date(current))
                current += step
                
        elif frequency_type == "weekly":
            if count <= 0: count = 1
            interval_days = 7.0 / count
            
            i = 0
            while True:
                offset_days = i * interval_days
                next_dt = start_dt + timedelta(days=offset_days)
                
                if next_dt > end_dt:
                    break
                
                dates.append(get_random_time_for_date(next_dt))
                i += 1
                
        # Sort dates just in case
        dates.sort()
        print(f"DEBUG: generate_schedule_dates inputs: start={start_date_str}, end={end_date_str}, type={frequency_type}, count={count}, w_start={window_start}, w_end={window_end}")
        print(f"DEBUG: Generated {len(dates)} dates. First: {dates[0] if dates else 'None'}")
        return dates
    except Exception as e:
        print(f"Error generating schedule: {e}")
        return []