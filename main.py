import os
import sqlite3
from datetime import datetime
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, BackgroundTasks

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
    conn.commit()
    conn.close()

init_db()

# 2. Worker to download media, save to disk, record in DB, and reply
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

# 3. Meta Webhook Handshake Verification (GET)
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        print("[Handshake] Webhook verified successfully with Meta!")
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(content="Token mismatch", status_code=403)

# 4. Inbound Webhook Listener (POST)
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