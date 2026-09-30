import os
import sqlite3
from datetime import datetime
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, BackgroundTasks
from pydantic import BaseModel

class FormSubmission(BaseModel):
    first_name: str
    phone_number: str
load_dotenv()

app = FastAPI(title="Dietary Study Bot")

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
DB_FILE = "test_study.db"

# 1. Initialize SQLite Database
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS test_meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            timestamp DATETIME,
            meal_type TEXT,
            caption TEXT,
            image_path TEXT
        )
    """)

    # Participants table: anchors their individual 15-day clock
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            phone_number TEXT PRIMARY KEY,
            first_name TEXT,
            start_timestamp INTEGER,
            status TEXT DEFAULT 'active'
        )
    """)

    conn.commit()
    conn.close()

init_db()

# 3. Worker to send the onboarding message via Meta Graph API
def send_welcome_message(phone_number: str, first_name: str):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

    message_body = (
        f"Hey {first_name}! 👋 Welcome to the 15-Day Energy Audit. You are officially in.\n\n"
        "For the next two weeks, this chat is your private, zero-judgment daily log. "
        "There is no calorie counting, no \"good\" or \"bad\" foods, and no clinical tracking apps. "
        "We just want to see how you naturally fuel your busy days.\n\n"
        "Your only task: Whenever you eat or drink *anything*, just snap a quick photo and send it right here. "
        "This includes your main meals, but just as importantly, we want to see the liquids that keep you going. "
        "Whether you grab a Gatorade at 11 AM, rely on a coffee to survive the 4 PM wall, or just sip on a traditional chaas, "
        "if you consume it, send a photo of it.\n\n"
        "To activate your log, snap a photo of your next meal, snack, or drink and send it over. Let’s get started! 📸"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message_body}
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            print(f"[Error] Failed to send welcome message to {phone_number}: {res.text}")
        else:
            print(f"[Success] Welcome message delivered to {phone_number} ({first_name})")
    except Exception as e:
        print(f"[Exception] Failed sending welcome ping: {e}")


# 2. Form Registration Endpoint
@app.post("/register")
async def register_volunteer(user: FormSubmission, bg_tasks: BackgroundTasks):
    current_ts = int(datetime.now().timestamp())
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # Save or update participant with their starting timestamp
        c.execute("""
            INSERT INTO users (phone_number, first_name, start_timestamp, status)
            VALUES (?, ?, ?, 'active')
            ON CONFLICT(phone_number) DO UPDATE SET
                first_name=excluded.first_name,
                start_timestamp=excluded.start_timestamp,
                status='active'
        """, (user.phone_number, user.first_name, current_ts))
        conn.commit()
        print(f"[User Registered] {user.first_name} ({user.phone_number}) registered at ts: {current_ts}")
        
        # Trigger WhatsApp message asynchronously so Google Apps Script doesn't block
        bg_tasks.add_task(send_welcome_message, user.phone_number, user.first_name)
    except Exception as e:
        print(f"[Database Error] Could not register user: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

    return {"status": "success", "message": f"Registered {user.first_name}"}

# 3. Worker to download media, save to disk, record in DB, and reply
def process_incoming_meal(media_id: str, sender: str, caption: str):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    try:
        # A. Fetch binary download URL from Meta
        media_info_url = f"https://graph.facebook.com/v20.0/{media_id}"
        meta_res = requests.get(media_info_url, headers=headers).json()
        download_url = meta_res.get("url")

        if not download_url:
            print(f"[Error] Could not retrieve media URL for ID: {media_id}")
            print(f"Meta Response: {meta_res}")
            return

        # B. Download raw binary image
        img_response = requests.get(download_url, headers=headers)
        if img_response.status_code != 200:
            print(f"[Error] Failed to download image bytes: {img_response.status_code}")
            return

        # Save to /images
        os.makedirs("images", exist_ok=True)
        filename = f"images/{sender}_{int(datetime.now().timestamp())}.jpg"
        with open(filename, "wb") as f:
            f.write(img_response.content)

        # C. Insert into SQLite
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO test_meal_logs (phone_number, timestamp, caption, image_path) VALUES (?, ?, ?, ?)",
            (sender, datetime.now(), caption, filename)
        )
        conn.commit()
        conn.close()
        print(f"[Success] Saved meal from {sender} -> {filename}")

        # D. Send WhatsApp confirmation reply
        ack_endpoint = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": sender,
            "type": "text",
            "text": {"body": "Logged! 📸 Meal recorded."}
        }
        requests.post(ack_endpoint, headers=headers, json=payload)

    except Exception as e:
        print(f"[Exception] Failed processing message from {sender}: {e}")

# 4. Meta Webhook Handshake Verification (GET)
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        print("[Handshake] Webhook verified successfully with Meta!")
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(content="Token mismatch", status_code=403)

# 5. Inbound Webhook Listener (POST)
@app.post("/webhook")
async def handle_incoming(request: Request, bg_tasks: BackgroundTasks):
    data = await request.json()
    
    # Force the terminal to print exactly what Meta is sending
    print("\n--- INCOMING PAYLOAD ---")
    print(data)
    
    try:
        entry = data.get("entry", [])[0]
        change = entry.get("changes", [])[0]["value"]
        
        if "messages" in change:
            msg = change["messages"][0]
            sender = msg["from"]

            # Scenario A: Participant sent an image
            if msg["type"] == "image":
                media_id = msg["image"]["id"]
                caption = msg["image"].get("caption", "No caption")
                bg_tasks.add_task(process_incoming_meal, media_id, sender, caption)

            # Scenario B: Participant replied with text only
            elif msg["type"] == "text":
                text_body = msg["text"]["body"]
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute(
                    "INSERT INTO test_meal_logs (phone_number, timestamp, caption, image_path) VALUES (?, ?, ?, ?)",
                    (sender, datetime.now(), text_body, "text_only")
                )
                conn.commit()
                conn.close()
                print(f"[Text Log] Logged text meal from {sender}: {text_body}")

                # Send brief text confirmation
                ack_endpoint = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
                headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
                payload = {
                    "messaging_product": "whatsapp",
                    "to": sender,
                    "type": "text",
                    "text": {"body": "Logged! 📝 Meal note recorded."}
                }
                requests.post(ack_endpoint, headers=headers, json=payload)

    except Exception as err:
        print(f"\n[Parsing Error] The script failed here: {err}")

    return {"status": "success"}