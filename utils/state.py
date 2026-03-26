import asyncio
import time

# Dictionary to store typing status: key -> timestamp (float)
# Keys:
# - "patient_{id}"
# - "psychologist_{patient_id}"
TYPING_STATUS = {}

def set_typing(key: str, is_typing: bool):
    if is_typing:
        TYPING_STATUS[key] = time.time()
    else:
        if key in TYPING_STATUS:
            del TYPING_STATUS[key]

def get_typing(key: str) -> bool:
    # Consider typing as valid if updated in the last 10 seconds
    if key in TYPING_STATUS:
        if time.time() - TYPING_STATUS[key] < 10:
            return True
        else:
            del TYPING_STATUS[key]
    return False
