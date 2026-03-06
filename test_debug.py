"""Debug: see exact API response for login attempt."""

import requests
from src.config import load_config

config = load_config()

url = "https://demo-api-capital.backend-capital.com/api/v1/session"
headers = {
    "X-CAP-API-KEY": config["capital"]["api_key"],
    "Content-Type": "application/json",
}
body = {
    "identifier": config["capital"]["email"],
    "password": config["capital"]["password"],
    "encryptedPassword": False,
}

print(f"URL: {url}")
print(f"Email: {config['capital']['email']}")
print(f"API key length: {len(config['capital']['api_key'])}")

resp = requests.post(url, json=body, headers=headers)
print(f"\nStatus: {resp.status_code}")
print(f"Headers: {dict(resp.headers)}")
print(f"Response: {resp.text}")
