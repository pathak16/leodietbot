import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")

# Enter your whitelisted test numbers (country code + number, no '+' or spaces)
TEST_NUMBERS = [
    "919326841356", # Your number
    # "91YYYYYYYYYY"  # Second tester
]

endpoint = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

for phone in TEST_NUMBERS:
    # Uses Meta's pre-approved 'hello_world' sandbox template
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"}
        }
    }
    response = requests.post(endpoint, headers=headers, json=payload)
    print(f"Sent to {phone}: {response.status_code} - {response.text}")