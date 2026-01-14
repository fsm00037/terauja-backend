import requests
import json

BASE_URL = "http://127.0.0.1:8001"

def test_auth_flow():
    # 1. Login as Admin
    print("1. Logging in as Admin...")
    login_payload = {"email": "admin@terauja.com", "password": "admin"}
    response = requests.post(f"{BASE_URL}/login", json=login_payload)
    if response.status_code != 200:
        print(f"Failed to login: {response.text}")
        return
    admin_token = response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("   Admin logged in successfully.")

    # 2. Create Patient
    print("\n2. Creating a test patient...")
    patient_payload = {
        "patient_code": "TEST-PATIENT-001",
        "access_code": "TEST-ACCESS-CODE-001"
    }
    # We need to handle potential 422 or 500 if patient already exists, or 409
    # Just try to create, if usually it auto-generates codes if missing, but we provide them to know them.
    # Actually create_patient takes a Patient model.
    # Let's try to post.
    response = requests.post(f"{BASE_URL}/patients", json=patient_payload, headers=admin_headers)
    if response.status_code == 200:
        patient_data = response.json()
        print(f"   Patient created: ID={patient_data['id']}, AccessCode={patient_data['access_code']}")
        patient_id = patient_data['id']
        access_code = patient_data['access_code']
    else:
        # If already exists, maybe we can list and find it, or just fail.
        # Let's list patients to find one if creation fails (likely unique constraint).
        print(f"   Creation failed ({response.status_code}), trying to fetch existing...")
        response = requests.get(f"{BASE_URL}/patients", headers=admin_headers)
        if response.status_code == 200:
            patients = response.json()
            if patients:
                p = patients[0]
                patient_id = p['id']
                access_code = p['access_code']
                print(f"   Using existing patient: ID={patient_id}, AccessCode={access_code}")
            else:
                print("   No patients found.")
                return
        else:
            print("   Failed to list patients.")
            return

    # 3. Authenticate as Patient
    print(f"\n3. Authenticating as Patient (Code: {access_code})...")
    response = requests.get(f"{BASE_URL}/auth/{access_code}")
    if response.status_code != 200:
        print(f"   Failed to authenticate patient: {response.text}")
        return
    
    patient_auth_data = response.json()
    if "access_token" not in patient_auth_data:
        print("   FAILURE: No access_token in response!")
        print(patient_auth_data)
        return
        
    patient_token = patient_auth_data["access_token"]
    print(f"   SUCCESS: Received access_token: {patient_token[:10]}...")

    # 4. Access Protected Endpoint (Messages)
    print(f"\n4. Accessing Protected Endpoint (GET /messages/{patient_id})...")
    patient_headers = {"Authorization": f"Bearer {patient_token}"}
    response = requests.get(f"{BASE_URL}/messages/{patient_id}", headers=patient_headers)
    
    if response.status_code == 200:
        print(f"   SUCCESS: Messages retrieved. Count: {len(response.json())}")
    else:
        print(f"   FAILURE: Status {response.status_code}")
        print(f"   Response: {response.text}")

if __name__ == "__main__":
    try:
        test_auth_flow()
    except Exception as e:
        print(f"An error occurred: {e}")
