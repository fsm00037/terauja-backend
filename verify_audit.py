
import requests
import json

BASE_URL = "http://127.0.0.1:8001"

def run():
    # 1. Login
    print("Logging in...")
    try:
        resp = requests.post(f"{BASE_URL}/login", json={"email": "admin@terauja.com", "password": "admin"})
        if resp.status_code != 200:
            print("Login failed:", resp.text)
            return
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    # 2. Create Note Test
    print("Testing Create Note...")
    # Need a patient first
    patients_resp = requests.get(f"{BASE_URL}/patients", headers=headers)
    if patients_resp.status_code == 200 and patients_resp.json():
        patient_id = patients_resp.json()[0]["id"]
        
        note_payload = {
            "patient_id": patient_id,
            "title": "Audit Test Note",
            "content": "Checking if this returns valid JSON",
            "color": "bg-white"
        }
        note_resp = requests.post(f"{BASE_URL}/notes", json=note_payload, headers=headers)
        print(f"Note Response Code: {note_resp.status_code}")
        print(f"Note Response Body: {note_resp.text}")
        
        if note_resp.status_code == 200:
            if note_resp.json().get("id"):
                print("SUCCESS: Note created and ID returned.")
            else:
                print("FAILURE: Empty or invalid note response.")
    else:
        print("Skipping Note test (no patients found)")

if __name__ == "__main__":
    run()
