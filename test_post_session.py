@
import httpx

url = 'http://localhost:8001/auth/login'
data = {'username': 'superadmin@psicouja.com', 'password': 'superadmin'}
r = httpx.post(url, data=data)
token = r.json().get('access_token')

url = 'http://localhost:8001/sessions'
headers = {'Authorization': f'Bearer {token}'}
payload = {
    'patient_id': 1,
    'duration': '1 min',
    'description': 'Test',
    'notes': 'Test notes',
    'chat_snapshot': []
}
r2 = httpx.post(url, headers=headers, json=payload)
print(r2.status_code)
print(r2.text)
@
