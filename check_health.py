import requests
import sys

try:
    print("Checking root endpoint...")
    r = requests.get("http://127.0.0.1:8001/")
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Root check failed: {e}")

try:
    print("\nChecking assignments endpoint (expect 401)...")
    r = requests.get("http://127.0.0.1:8001/assignments/my-pending")
    print(f"Status: {r.status_code}")
except Exception as e:
    print(f"Assignments check failed: {e}")
