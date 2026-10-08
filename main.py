import os
import time
from analysis import run_gemini_vision_pipeline
import sqlite3
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, BackgroundTasks
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

app = FastAPI(title="Dietary Study Bot")

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

HARDCODED_NUDGES = {
    "breakfast_nudge_1": "Good Morning!☀️ Whenever you get a breather, drop a quick photo of your breakfast. Waiting! ",
    "breakfast_nudge_2": "Starving has never lead to better work 😒 Go grab something to eat and show us proof!",
    "lunch_nudge_1": "What's for lunch today?",
    "lunch_nudge_2": "I know being behind on work is bad. But know what's worse? Acidity.",
    "dinner_nudge_1": "What's for dinner?",
    "dinner_nudge_2": "If it's taking this long, it has to be something yummy. How dare you hide!?",
}

app.mount("/app/data/images", StaticFiles(directory="/app/data/images"), name="images")


@app.get("/admin/dashboard", response_class=HTMLResponse)
def view_dashboard():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    query = """
    SELECT 
        l.id, l.phone_number, l.timestamp, l.caption, l.image_path,
        n.identified_items, n.meal_type, n.food_source_type, n.staple_format,
        n.protein_grams, n.carbs_grams, n.fat_grams, n.fiber_grams,
        n.protein_source_present, n.protein_source_type,
        n.primary_fuel_source, n.crash_risk_level, n.is_caffeine_or_sugar_crutch,
        n.raw_json
    FROM test_meal_logs l
    LEFT JOIN meal_nutrition n ON l.id = n.meal_log_id
    WHERE l.id = ?
    """
    c.execute(query, (meal_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Meal log not found")

    # Format items list
    items_list = []
    if row["identified_items"]:
        try:
            items_list = json.loads(row["identified_items"])
        except Exception:
            items_list = [row["identified_items"]]

    items_chips = "".join(
        [
            (
                f'<span style="display: inline-block; background: #e2e8f0; color:'
                " #1e293b; padding: 4px 10px; border-radius: 999px; margin-right:"
                f' 6px; font-size: 13px; font-weight: 500;">{item}</span>'
            )
            for item in items_list
        ]
    )

    # Risk coloring
    risk = row["crash_risk_level"] or "N/A"
    risk_color = (
        "#ef4444" if risk == "High" else ("#f59e0b" if risk == "Medium" else "#10b981")
    )

    # Pretty format raw JSON for inspection
    formatted_json = "-"
    if row["raw_json"]:
        try:
            formatted_json = json.dumps(json.loads(row["raw_json"]), indent=2)
        except Exception:
            formatted_json = row["raw_json"]

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <title>Meal #{row['id']} Details</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; margin: 0; padding: 24px; color: #0f172a; }}
        .container {{ max-width: 900px; margin: auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ padding: 18px 24px; background: #0f172a; color: white; display: flex; justify-content: space-between; align-items: center; }}
        .content {{ display: flex; flex-wrap: wrap; gap: 24px; padding: 24px; }}
        .col-left {{ flex: 1; min-width: 280px; }}
        .col-right {{ flex: 1.5; min-width: 320px; }}
        .img-box {{ width: 100%; max-height: 420px; object-fit: contain; background: #000; border-radius: 8px; }}
        .metric-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
        .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 10px; text-align: center; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
        pre {{ background: #1e293b; color: #f8fafc; padding: 12px; border-radius: 6px; font-size: 11px; overflow-x: auto; max-height: 200px; }}
    </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
            <div>
                <a href="/admin/dashboard" style="color: #94a3b8; text-decoration: none; font-size: 13px;">&larr; Back to Dashboard</a>
                <h2 style="margin: 4px 0 0 0; font-size: 18px;">Meal #{row['id']} — Participant {row['phone_number']}</h2>
            </div>
            <span style="font-size: 12px; color: #94a3b8;">{str(row['timestamp'])[:19]}</span>
        </div>

        <div class="content">
            <!-- Left: Photo & Raw Caption -->
            <div class="col-left">
                <img src="/{row['image_path']}" class="img-box" onerror="this.src='https://placehold.co/400x300?text=No+Photo'">
                <div style="margin-top: 14px;">
                    <span style="font-size: 12px; color: #64748b; font-weight: 600;">USER CAPTION</span>
                    <p style="margin: 4px 0; font-size: 14px; font-style: italic;">"{row['caption'] or 'No caption provided'}"</p>
                </div>
            </div>

            <!-- Right: Nutrition Breakdown & Behavioral Drivers -->
            <div class="col-right">
                <div class="metric-card">
                    <span style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;">Identified Foods</span>
                    <div style="margin-top: 8px;">{items_chips or 'None identified'}</div>
                </div>

                <div class="metric-card">
                    <span style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;">Nutritional Breakdown (Estimated)</span>
                    <div class="grid-4">
                        <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                            <div style="font-size: 11px; color: #64748b;">Protein</div>
                            <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['protein_grams'] or 0}g</div>
                        </div>
                        <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                            <div style="font-size: 11px; color: #64748b;">Carbs</div>
                            <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['carbs_grams'] or 0}g</div>
                        </div>
                        <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                            <div style="font-size: 11px; color: #64748b;">Fat</div>
                            <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['fat_grams'] or 0}g</div>
                        </div>
                        <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                            <div style="font-size: 11px; color: #64748b;">Fiber</div>
                            <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['fiber_grams'] or 0}g</div>
                        </div>
                    </div>
                </div>

                <div class="metric-card">
                    <span style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;">Study Insights & Behavioral Markers</span>
                    <div style="margin-top: 10px; font-size: 13px; line-height: 1.8;">
                        <div><b>Meal Category:</b> {row['meal_type'] or 'N/A'} ({row['food_source_type'] or 'N/A'})</div>
                        <div><b>Staple Format:</b> <span class="badge" style="background: #e2e8f0;">{row['staple_format'] or 'N/A'}</span></div>
                        <div><b>Fuel Classification:</b> <span class="badge" style="background: #dbeafe; color: #1e40af;">{row['primary_fuel_source'] or 'N/A'}</span></div>
                        <div><b>Glycemic Crash Risk:</b> <span class="badge" style="background: {risk_color}22; color: {risk_color};">{risk}</span></div>
                        <div><b>Sugar / Stimulant Crutch:</b> {'🚨 Yes' if row['is_caffeine_or_sugar_crutch'] else 'No'}</div>
                        <div><b>Protein Source Anchor:</b> {row['protein_source_type'] or 'None'}</div>
                    </div>
                </div>

                <details style="font-size: 12px; color: #64748b; margin-top: 10px;">
                    <summary style="cursor: pointer; font-weight: 600;">View Raw Gemini JSON Output</summary>
                    <pre>{formatted_json}</pre>
                </details>
            </div>
        </div>
    </div>
    </body>
    </html>
    """


@app.get("/admin/meal/{meal_id}", response_class=HTMLResponse)
def meal_detail_page(meal_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = """
    SELECT 
        l.id, l.phone_number, l.timestamp, l.caption, l.image_path,
        n.identified_items, n.meal_type, n.food_source_type, n.staple_format,
        n.protein_grams, n.carbs_grams, n.fat_grams, n.fiber_grams,
        n.protein_source_present, n.protein_source_type,
        n.primary_fuel_source, n.crash_risk_level, n.is_caffeine_or_sugar_crutch,
        n.raw_json
    FROM test_meal_logs l
    LEFT JOIN meal_nutrition n ON l.id = n.meal_log_id
    WHERE l.id = ?
    """
    c.execute(query, (meal_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Meal log not found")

    # Format items list
    items_list = []
    if row["identified_items"]:
        try:
            items_list = json.loads(row["identified_items"])
        except Exception:
            items_list = [row["identified_items"]]

    items_chips = "".join(
        [
            (
                f'<span style="display: inline-block; background: #e2e8f0; color:'
                " #1e293b; padding: 4px 10px; border-radius: 999px; margin-right:"
                f' 6px; font-size: 13px; font-weight: 500;">{item}</span>'
            )
            for item in items_list
        ]
    )

    # Risk coloring
    risk = row["crash_risk_level"] or "N/A"
    risk_color = (
        "#ef4444" if risk == "High" else ("#f59e0b" if risk == "Medium" else "#10b981")
    )

    # Pretty format raw JSON for inspection
    formatted_json = "-"
    if row["raw_json"]:
        try:
            formatted_json = json.dumps(json.loads(row["raw_json"]), indent=2)
        except Exception:
            formatted_json = row["raw_json"]

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Meal #{row['id']} Details</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; margin: 0; padding: 24px; color: #0f172a; }}
            .container {{ max-width: 900px; margin: auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; }}
            .header {{ padding: 18px 24px; background: #0f172a; color: white; display: flex; justify-content: space-between; align-items: center; }}
            .content {{ display: flex; flex-wrap: wrap; gap: 24px; padding: 24px; }}
            .col-left {{ flex: 1; min-width: 280px; }}
            .col-right {{ flex: 1.5; min-width: 320px; }}
            .img-box {{ width: 100%; max-height: 420px; object-fit: contain; background: #000; border-radius: 8px; }}
            .metric-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
            .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 10px; text-align: center; }}
            .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
            pre {{ background: #1e293b; color: #f8fafc; padding: 12px; border-radius: 6px; font-size: 11px; overflow-x: auto; max-height: 200px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <a href="/admin/dashboard" style="color: #94a3b8; text-decoration: none; font-size: 13px;">&larr; Back to Dashboard</a>
                    <h2 style="margin: 4px 0 0 0; font-size: 18px;">Meal #{row['id']} — Participant {row['phone_number']}</h2>
                </div>
                <span style="font-size: 12px; color: #94a3b8;">{str(row['timestamp'])[:19]}</span>
            </div>

            <div class="content">
                <!-- Left: Photo & Raw Caption -->
                <div class="col-left">
                    <img src="/{row['image_path']}" class="img-box" onerror="this.src='https://placehold.co/400x300?text=No+Photo'">
                    <div style="margin-top: 14px;">
                        <span style="font-size: 12px; color: #64748b; font-weight: 600;">USER CAPTION</span>
                        <p style="margin: 4px 0; font-size: 14px; font-style: italic;">"{row['caption'] or 'No caption provided'}"</p>
                    </div>
                </div>

                <!-- Right: Nutrition Breakdown & Behavioral Drivers -->
                <div class="col-right">
                    <div class="metric-card">
                        <span style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;">Identified Foods</span>
                        <div style="margin-top: 8px;">{items_chips or 'None identified'}</div>
                    </div>

                    <div class="metric-card">
                        <span style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;">Nutritional Breakdown (Estimated)</span>
                        <div class="grid-4">
                            <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                                <div style="font-size: 11px; color: #64748b;">Protein</div>
                                <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['protein_grams'] or 0}g</div>
                            </div>
                            <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                                <div style="font-size: 11px; color: #64748b;">Carbs</div>
                                <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['carbs_grams'] or 0}g</div>
                            </div>
                            <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                                <div style="font-size: 11px; color: #64748b;">Fat</div>
                                <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['fat_grams'] or 0}g</div>
                            </div>
                            <div style="background: white; border: 1px solid #e2e8f0; padding: 8px; border-radius: 6px;">
                                <div style="font-size: 11px; color: #64748b;">Fiber</div>
                                <div style="font-size: 18px; font-weight: bold; color: #0f172a;">{row['fiber_grams'] or 0}g</div>
                            </div>
                        </div>
                    </div>

                    <div class="metric-card">
                        <span style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase;">Study Insights & Behavioral Markers</span>
                        <div style="margin-top: 10px; font-size: 13px; line-height: 1.8;">
                            <div><b>Meal Category:</b> {row['meal_type'] or 'N/A'} ({row['food_source_type'] or 'N/A'})</div>
                            <div><b>Staple Format:</b> <span class="badge" style="background: #e2e8f0;">{row['staple_format'] or 'N/A'}</span></div>
                            <div><b>Fuel Classification:</b> <span class="badge" style="background: #dbeafe; color: #1e40af;">{row['primary_fuel_source'] or 'N/A'}</span></div>
                            <div><b>Glycemic Crash Risk:</b> <span class="badge" style="background: {risk_color}22; color: {risk_color};">{risk}</span></div>
                            <div><b>Sugar / Stimulant Crutch:</b> {'🚨 Yes' if row['is_caffeine_or_sugar_crutch'] else 'No'}</div>
                            <div><b>Protein Source Anchor:</b> {row['protein_source_type'] or 'None'}</div>
                        </div>
                    </div>

                    <details style="font-size: 12px; color: #64748b; margin-top: 10px;">
                        <summary style="cursor: pointer; font-weight: 600;">View Raw Gemini JSON Output</summary>
                        <pre>{formatted_json}</pre>
                    </details>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def init_storage():
    target_dir = "/app/data"
    if os.path.exists(target_dir):
        # Try candidate database names in case one already exists with bad permissions or as a directory
        for db_name in ["study.db", "test_study.db"]:
            db_path = os.path.join(target_dir, db_name)
            if os.path.isdir(db_path):
                db_path = os.path.join(db_path, "study.db")
            try:
                conn = sqlite3.connect(db_path)
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS _test_check (id INTEGER PRIMARY KEY)"
                )
                conn.close()
                images_dir = os.path.join(target_dir, "images")
                os.makedirs(images_dir, exist_ok=True)
                print(
                    f"[Storage] Persistent volume active. Connected to SQLite: {db_path}"
                )
                return target_dir, images_dir, db_path
            except Exception as e:
                print(f"[Storage] Cannot use {db_path}: {e}")

    os.makedirs("images", exist_ok=True)
    print("[Storage] Using local fallback: test_study.db")
    return ".", "images", "test_study.db"


DATA_DIR, IMAGE_DIR, DB_FILE = init_storage()
app.mount("/view-images", StaticFiles(directory=IMAGE_DIR), name="images")


# 1. Initialize SQLite Database
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS test_meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            timestamp DATETIME,
            meal_type TEXT,
            caption TEXT,
            image_path TEXT
        )
    """
    )

    # Participants table: anchors their individual 15-day clock
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            phone_number TEXT PRIMARY KEY,
            first_name TEXT,
            start_timestamp INTEGER,
            status TEXT DEFAULT 'active'
        )
    """
    )

    c.execute(
        """CREATE TABLE IF NOT EXISTS meal_nutrition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_log_id INTEGER,
    phone_number TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    identified_items TEXT,              -- JSON string list of items
    meal_type TEXT,
    food_source_type TEXT,
    staple_format TEXT,
    protein_grams REAL,
    carbs_grams REAL,
    fat_grams REAL,
    fiber_grams REAL,
    protein_source_present BOOLEAN,
    protein_source_type TEXT,
    is_caffeine_or_sugar_crutch BOOLEAN,
    primary_fuel_source TEXT,
    crash_risk_level TEXT,
    raw_json TEXT
    )
    """
    )

    conn.commit()
    conn.close()


init_db()


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

        # Save to images directory
        filename = os.path.join(
            IMAGE_DIR, f"{sender}_{int(datetime.now().timestamp())}.jpg"
        )
        with open(filename, "wb") as f:
            f.write(img_response.content)

        # C. Insert into SQLite
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO test_meal_logs (phone_number, timestamp, caption, image_path) VALUES (?, ?, ?, ?)",
            (sender, datetime.now(), caption, filename),
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
            "text": {"body": "Logged! 📸 Meal recorded."},
        }
        requests.post(ack_endpoint, headers=headers, json=payload)

    except Exception as e:
        print(f"[Exception] Failed processing message from {sender}: {e}")

    # 4. Real-time Gemini Processing Pipeline
    try:
        print(f"[Gemini] Analyzing image for meal #{meal_log_id} ({sender})...")
        analysis = run_gemini_vision_pipeline(filename, caption)

        c.execute(
            """
                INSERT INTO meal_nutrition (
                    meal_log_id, phone_number, identified_items, meal_type,
                    food_source_type, staple_format, protein_grams, carbs_grams,
                    fat_grams, fiber_grams, protein_source_present, protein_source_type,
                    is_caffeine_or_sugar_crutch, primary_fuel_source, crash_risk_level, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meal_log_id,
                sender,
                json.dumps(analysis.get("identified_items", [])),
                analysis.get("meal_type"),
                analysis.get("food_source_type"),
                analysis.get("staple_format"),
                analysis.get("estimated_protein_grams", 0.0),
                analysis.get("estimated_carbs_grams", 0.0),
                analysis.get("estimated_fat_grams", 0.0),
                analysis.get("estimated_fiber_grams", 0.0),
                analysis.get("protein_source_present", False),
                analysis.get("protein_source_type"),
                analysis.get("is_caffeine_or_sugar_crutch", False),
                analysis.get("primary_fuel_source"),
                analysis.get("crash_risk_level"),
                json.dumps(analysis),
            ),
        )
        conn.commit()
        print(
            f"[Gemini] Success: {analysis.get('identified_items')} | Protein:"
            f" {analysis.get('estimated_protein_grams')}g | Fuel:"
            f" {analysis.get('primary_fuel_source')}"
        )
    except Exception as e:
        print(f"[Gemini Error] Processing failed for meal #{meal_log_id}: {e}")
    finally:
        conn.close()


# Admin Viewers to easily see users and meals in browser
@app.get("/admin/users", response_class=HTMLResponse)
async def view_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT phone_number, start_timestamp, status FROM users ORDER BY start_timestamp DESC"
    )
    rows = c.fetchall()
    conn.close()

    html = "<html><head><title>Participants</title><style>body{font-family:sans-serif;padding:20px;}table{border-collapse:collapse;width:100%;max-width:600px;}th,td{border:1px solid #ccc;padding:8px;text-align:left;}th{background:#f4f4f4;}</style></head><body>"
    html += f"<h2>Registered Participants ({len(rows)})</h2>"
    html += "<p><a href='/admin/meals'>View Logged Meals &amp; Photos &rarr;</a></p>"
    html += (
        "<table><tr><th>Phone Number</th><th>Registration Time</th><th>Status</th></tr>"
    )
    for phone, ts, status in rows:
        time_str = (
            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "N/A"
        )
        html += f"<tr><td>{phone}</td><td>{time_str}</td><td>{status}</td></tr>"
    html += "</table></body></html>"
    return html


@app.get("/admin/meals", response_class=HTMLResponse)
async def view_meals():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT phone_number, timestamp, caption, image_path FROM test_meal_logs ORDER BY timestamp DESC"
    )
    rows = c.fetchall()
    conn.close()

    html = "<html><head><title>Logged Meals</title><style>body{font-family:sans-serif;padding:20px;}table{border-collapse:collapse;width:100%;}th,td{border:1px solid #ccc;padding:8px;text-align:left;}th{background:#f4f4f4;}img{max-width:120px;border-radius:4px;}</style></head><body>"
    html += f"<h2>Logged Meals ({len(rows)})</h2>"
    html += "<p><a href='/admin/users'>&larr; View Participants</a></p>"
    html += (
        "<table><tr><th>Phone</th><th>Timestamp</th><th>Caption</th><th>Image</th></tr>"
    )
    for phone, ts, caption, img_path in rows:
        img_html = "Text only"
        if img_path and img_path != "text_only":
            fname = os.path.basename(img_path)
            img_html = f"<a href='/view-images/{fname}' target='_blank'><img src='/view-images/{fname}'/></a>"
        html += f"<tr><td>{phone}</td><td>{ts}</td><td>{caption or ''}</td><td>{img_html}</td></tr>"
    html += "</table></body></html>"
    return html


# 4. Meta Webhook Handshake Verification (GET)
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == VERIFY_TOKEN
    ):
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

            # --- ADD THIS EXPIRATION CHECK ---
            msg_timestamp = int(msg["timestamp"])
            current_time = int(time.time())

            # If the message is older than 120 seconds, ignore it
            if current_time - msg_timestamp > 120:
                print(f"Ignored backlogged message from {sender}")
                return {"status": "success"}

            # Scenario A: Participant sent an image
            if msg["type"] == "image":
                media_id = msg["image"]["id"]
                caption = msg["image"].get("caption", "").strip()

                if caption:
                    bg_tasks.add_task(process_incoming_meal, media_id, sender, caption)

                else:
                    # No caption -> reject the log and ask for one
                    ack_endpoint = (
                        f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
                    )
                    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": sender,
                        "type": "text",
                        "text": {
                            "body": "Oops! We need a quick description to log this meal. 📸 Please send the photo again and type what it is in the caption!"
                        },
                    }
                    requests.post(ack_endpoint, headers=headers, json=payload)
                    print(f"[Rejected] Image from {sender} had no caption.")

            # Scenario B: Participant replied with text
            elif msg["type"] == "text":
                text_body = msg["text"]["body"]
                sender = msg["from"]
                current_ts = int(datetime.now().timestamp())

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()

                # --- THE ZERO-COST ONBOARDING TRIGGER ---
                if "ready to start" in text_body.lower() or text_body.lower() == "hi":
                    # 1. Register them in the database
                    c.execute(
                        """
                        INSERT INTO users (phone_number, start_timestamp, status)
                        VALUES (?, ?, 'active')
                        ON CONFLICT(phone_number) DO NOTHING
                    """,
                        (sender, current_ts),
                    )
                    conn.commit()

                    # 2. Send the Free Welcome Message
                    welcome_body = (
                        "Helloooo! Yayy, you are officially in! \n\n"
                        "You know what to do. For the next 15 days, whenever you eat or drink *anything*, just snap a quick photo and send it right here. "
                        "Let’s get starteddd!"
                    )

                    ack_endpoint = (
                        f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
                    )
                    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": sender,
                        "type": "text",
                        "text": {"body": welcome_body},
                    }
                    requests.post(ack_endpoint, headers=headers, json=payload)
                    print(
                        f"[Onboarded] User {sender} successfully registered and welcomed!"
                    )

                # --- STANDARD TEXT MEAL LOGGING ---
                else:
                    c.execute(
                        "INSERT INTO test_meal_logs (phone_number, timestamp, caption, image_path) VALUES (?, ?, ?, ?)",
                        (sender, datetime.now(), text_body, "text_only"),
                    )
                    conn.commit()

                    ack_endpoint = (
                        f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
                    )
                    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": sender,
                        "type": "text",
                        "text": {"body": "Logged! 📝 Meal note recorded."},
                    }
                    requests.post(ack_endpoint, headers=headers, json=payload)

                conn.close()

    except Exception as err:
        print(f"\n[Parsing Error] The script failed here: {err}")

    return {"status": "success"}

    # def push_template_message(phone_number, template_name):
    endpoint = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        "template": {"name": template_name, "language": {"code": "en"}},
    }
    try:
        res = requests.post(endpoint, headers=headers, json=payload)
        if res.status_code == 200:
            print(f"[API Success] Meta accepted {template_name} for {phone_number}")
        else:
            print(f"[API Error] Meta rejected {phone_number}: {res.text}")

    except Exception as e:
        print(f"[API Error] Failed to send {template_name} to {phone_number}: {e}")


def push_text_nudge(phone_number, nudge_key):
    raw_text = HARDCODED_NUDGES.get(nudge_key, "Just checking in on your meals!")

    endpoint = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": raw_text},
    }

    res = requests.post(endpoint, headers=headers, json=payload)
    if res.status_code == 200:
        print(f"[Success] Sent raw text nudge ({nudge_key}) to {phone_number}")
    else:
        print(f"[API Error] Meta rejected nudge to {phone_number}: {res.text}")


def run_fixed_reminders(nudge_key):
    """Fires at exact times regardless of user activity."""
    print(f"[Scheduler] Executing fixed blast: {nudge_key}")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT phone_number FROM users WHERE status = 'active'")
    users = c.fetchall()
    conn.close()

    print(f"[Scheduler] Found {len(users)} active user(s) in DB ({DB_FILE}).")
    if not users:
        print(f"[Scheduler] No active users to send {nudge_key} to.")
        return

    for (phone_number,) in users:
        push_text_nudge(phone_number, nudge_key)
        print(f" -> Sent fixed reminder to {phone_number}")


def run_conditional_nudges(hours_of_silence, nudge_key):
    """Checks DB and only fires if the user has been silent for X hours."""
    print(f"[Scheduler] Checking for users silent for {hours_of_silence} hours...")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        SELECT u.phone_number, u.start_timestamp, MAX(m.timestamp) as last_meal_time
        FROM users u
        LEFT JOIN test_meal_logs m ON u.phone_number = m.phone_number
        WHERE u.status = 'active'
        GROUP BY u.phone_number
    """
    )
    users_data = c.fetchall()
    conn.close()

    print(f"[Scheduler] Found {len(users_data)} active user(s) to check.")

    now = datetime.now()
    silence_threshold = timedelta(hours=hours_of_silence)

    for phone_number, start_ts, last_meal_time_str in users_data:
        if last_meal_time_str:
            try:
                last_activity = datetime.fromisoformat(last_meal_time_str)
            except ValueError:
                last_activity = datetime.strptime(
                    last_meal_time_str.split(".")[0], "%Y-%m-%d %H:%M:%S"
                )
        else:
            last_activity = datetime.fromtimestamp(start_ts)

        if (now - last_activity) >= silence_threshold:
            push_text_nudge(phone_number, nudge_key)
            print(f" -> Sent missed-meal nudge to {phone_number}")


# --- STARTUP EVENT ---


@app.on_event("startup")
def start_scheduler():
    # Force the scheduler to operate on IST regardless of Railway's server location
    ist_tz = pytz.timezone("Asia/Kolkata")
    scheduler = BackgroundScheduler(timezone=ist_tz)

    # 1. The Fixed Reminders (9:00 AM, 1:00 PM, 8:00 PM)
    scheduler.add_job(
        run_fixed_reminders,
        "cron",
        hour=9,
        minute=0,
        misfire_grace_time=3600,
        args=["breakfast_nudge_1"],
    )
    scheduler.add_job(
        run_fixed_reminders,
        "cron",
        hour=12,
        minute=45,
        misfire_grace_time=3600,
        args=["lunch_nudge_1"],
    )
    scheduler.add_job(
        run_fixed_reminders,
        "cron",
        hour=20,
        minute=0,
        misfire_grace_time=3600,
        args=["dinner_nudge_1"],
    )

    # 2. The Conditional Nudges (11:00 AM, 3:00 PM, 10:00 PM)
    # Triggers exactly 2 hours later, passing '2' as the hours_of_silence argument
    scheduler.add_job(
        run_conditional_nudges,
        "cron",
        hour=11,
        minute=0,
        misfire_grace_time=3600,
        args=[2, "breakfast_nudge_2"],
    )
    scheduler.add_job(
        run_conditional_nudges,
        "cron",
        hour=14,
        minute=30,
        misfire_grace_time=3600,
        args=[2, "lunch_nudge_2"],
    )
    scheduler.add_job(
        run_conditional_nudges,
        "cron",
        hour=22,
        minute=0,
        misfire_grace_time=3600,
        args=[2, "dinner_nudge_2"],
    )

    scheduler.start()
    print("[System] Background scheduler initialized on IST time.")
