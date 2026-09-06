import os
import requests
import time

GO_URL = "http://localhost:9380"

print("Logging in...")
res = requests.post(f"{GO_URL}/api/v1/user/login", json={"email": "test@example.com", "password": "Password123"})
if res.status_code != 200:
    print("Login failed:", res.text); exit(1)
token = res.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

ds_id = "25ffda3f-77f2-477a-93dc-a18365caacf5"

print("Creating Chat Session...")
res = requests.post(f"{GO_URL}/api/v1/chat/session", json={"dataset_id": ds_id, "name": "Demo Session"}, headers=headers)
session_id = res.json()["id"]
print(f"Session ID: {session_id}")

print("Asking question...")
res = requests.post(f"{GO_URL}/api/v1/chat/completions", json={
    "session_id": session_id,
    "message": "What is the main topic of this presentation?",
}, headers=headers)

if res.status_code == 200:
    print("\n[ANSWER]")
    print(res.json()["answer"])
    print("\n[REFERENCES]")
    for ref in res.json().get("references", []):
        print(f"- Chunk: {ref['chunk_id']} (Score: {ref['score']})")
else:
    print("Chat failed:", res.text)
