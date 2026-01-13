import requests
import json

url = "http://127.0.0.1:8001/chat/recommendations"
headers = {"Content-Type": "application/json"}
data = {
    "messages": [
        {"role": "user", "content": "Estoy triste y no quiero hacer nada."},
        {"role": "assistant", "content": "Entiendo que te sientas así. ¿Ha pasado algo recientemente que te haga sentir de esa manera?"},
        {"role": "user", "content": "No, es solo que me siento vacío."}
    ]
}

try:
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print("Success! Recommendations:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"Failed with status {response.status_code}: {response.text}")
except Exception as e:
    print(f"Error: {e}")
