import os
import json
import time
from analysis import run_gemini_vision_pipeline
import sqlite3
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, BackgroundTasks
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
import io
from PIL import Image
import html as html_escape
from pydantic import BaseModel
from datetime import datetime, time as dtime, timedelta
import html as html_escape
from fastapi import Request
from fastapi.responses import HTMLResponse

load_dotenv()

app = FastAPI(title="Dietary Study Bot")

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
from fastapi.staticfiles import StaticFiles

HARDCODED_NUDGES = {
    "breakfast_nudge_1": "Good Morning!☀️ Whenever you get a breather, drop a quick photo of your breakfast. Waiting! ",
    "breakfast_nudge_2": "Starving has never lead to better work 😒 Go grab something to eat and show us proof!",
    "lunch_nudge_1": "What's for lunch today?",
    "lunch_nudge_2": "I know being behind on work is bad. But know what's worse? Acidity.",
    "dinner_nudge_1": "What's for dinner?",
    "dinner_nudge_2": "If it's taking this long, it has to be something yummy. How dare you hide!?",
}


class UpdateMealTypeRequest(BaseModel):
    meal_log_id: int
    meal_type: str


@app.post("/admin/update-meal-type")
def update_meal_type(req: UpdateMealTypeRequest):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "UPDATE test_meal_logs SET meal_type = ? WHERE id = ?",
        (req.meal_type, req.meal_log_id),
    )
    conn.commit()
    conn.close()
    return {"status": "success", "meal_type": req.meal_type}


# @app.get("/admin/dashboard", response_class=HTMLResponse)
# def view_dashboard(
#     request: Request,
#     phone_filter: str = "ALL",
#     day_filter: str = "ALL",
#     meal_filter: str = "ALL",
# ):
#     conn = sqlite3.connect(DB_FILE)
#     c = conn.cursor()

#     # 1. Fetch participants, day 1 anchor, and last interaction
#     c.execute(
#         """
#         SELECT
#             u.phone_number,
#             u.start_timestamp,
#             u.status,
#             MIN(m.timestamp) AS first_interaction,
#             MAX(m.timestamp) AS last_interaction
#         FROM users u
#         LEFT JOIN test_meal_logs m ON u.phone_number = m.phone_number
#         GROUP BY u.phone_number
#         ORDER BY last_interaction DESC NULLS LAST
#     """
#     )
#     users = c.fetchall()

#     # 2. Fetch logged meals and drinks
#     c.execute(
#         "SELECT phone_number, timestamp, caption, image_path FROM test_meal_logs"
#         " ORDER BY timestamp DESC"
#     )
#     logs = c.fetchall()
#     conn.close()

#     c.execute("SELECT phone_number, start_timestamp FROM users")
#     user_starts = {}
#     for u_phone, start_ts in c.fetchall():
#         if start_ts:
#             try:
#                 user_starts[u_phone] = datetime.fromtimestamp(float(start_ts)).date()
#             except Exception:
#                 user_starts[u_phone] = datetime.now().date()

#   # 2. Fetch distinct phone numbers for the filter dropdown
#     c.execute(
#         "SELECT DISTINCT phone_number FROM test_meal_logs ORDER BY phone_number"
#     )
#     all_phones = [row[0] for row in c.fetchall()]

#     def parse_dt(val):
#         if not val:
#             return None
#         if isinstance(val, (int, float)):
#             return datetime.fromtimestamp(val)
#         if isinstance(val, str):
#             for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
#                 try:
#                     return datetime.strptime(val[:19], fmt)
#                 except ValueError:
#                     pass
#         return None

#     now = datetime.now()
#     today_date = now.date()
#     cutoff_24h = now - timedelta(hours=24)

#     page_html = """<!DOCTYPE html>
#     <html>
#     <head>
#         <title>Dietary Study Logs</title>
#         <style>
#             body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 24px; background: #f8fafc; color: #1e293b; }
#             h2 { margin-top: 32px; color: #0f172a; }
#             table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }
#             th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 14px; vertical-align: top; }
#             th { background: #0f172a; color: white; }
#             img { border-radius: 6px; object-fit: cover; }
#             .search-box {
#                 width: 100%;
#                 max-width: 400px;
#                 padding: 10px 14px;
#                 margin-bottom: 20px;
#                 border: 1px solid #cbd5e1;
#                 border-radius: 6px;
#                 font-size: 14px;
#                 outline: none;
#                 box-sizing: border-box;
#             }
#             .search-box:focus {
#                 border-color: #2563eb;
#                 box-shadow: 0 0 0 2px rgba(37,99,235,0.2);
#             }
#             details summary {
#                 cursor: pointer;
#                 color: #2563eb;
#                 font-weight: 600;
#                 font-size: 13px;
#                 outline: none;
#             }
#             details summary:hover {
#                 text-decoration: underline;
#             }
#             pre.json-box {
#                 background: #f1f5f9;
#                 border: 1px solid #cbd5e1;
#                 border-radius: 6px;
#                 padding: 10px;
#                 font-size: 11px;
#                 white-space: pre-wrap;
#                 word-break: break-word;
#                 max-height: 250px;
#                 overflow-y: auto;
#                 margin-top: 8px;
#             }
#         </style>
#     </head>
#     <body>
#         <h2>Registered Participants</h2>
#         <input
#             type="text"
#             id="phoneSearch"
#             class="search-box"
#             placeholder="Search by phone number..."
#             onkeyup="filterByPhone()"
#         />
#         <table id="participantsTable">
#             <tr>
#                 <th>Phone Number</th>
#                 <th>Registered At</th>
#                 <th>Study Day</th>
#                 <th>Status</th>
#                 <th>Last Interaction</th>
#             </tr>
#     """

#     # Table 1: Participants
#     for phone, start_ts, db_status, first_int, last_int in users:
#         reg_dt = parse_dt(start_ts)
#         first_dt = parse_dt(first_int)
#         last_dt = parse_dt(last_int)

#         reg_str = reg_dt.strftime("%Y-%m-%d %H:%M:%S") if reg_dt else "N/A"
#         last_str = last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else "Never logged"

#         latest_activity = last_dt or reg_dt
#         is_inactive = bool(latest_activity and latest_activity < cutoff_24h)

#         if is_inactive:
#             status_label = "inactive"
#             badge_style = "background:#fee2e2; color:#ef4444; border:1px solid #fca5a5;"
#         else:
#             status_label = "active"
#             badge_style = "background:#dcfce7; color:#16a34a; border:1px solid #86efac;"

#         if first_dt:

#             anchor_date = last_dt.date() if (is_inactive and last_dt) else today_date
#             day_num = (anchor_date - first_dt.date()).days + 1

#             if day_num > 15:
#                 day_badge = (
#                     "<span style='color:#64748b; font-weight:600;'>Completed Day"
#                     f" {day_num}</span>"
#                 )
#             elif is_inactive:
#                 day_badge = (
#                     f"<span style='color:#ef4444; font-weight:700;'>Paused at Day"
#                     f" {day_num}</span>"
#                 )
#             else:
#                 day_badge = f"<span style='color:#2563eb; font-weight:700;'>Day {day_num}</span>"
#         else:
#             day_badge = "<span style='color:#94a3b8;'>Not started</span>"

#         page_html += f"""
#             <tr style="border-bottom: 1px solid #e2e8f0;">
#                 <td style="padding:12px; font-family:monospace;">{phone}</td>
#                 <td style="padding:12px; color:#475569;">{reg_str}</td>
#                 <td style="padding:12px;">{day_badge}</td>
#                 <td style="padding:12px;">
#                     <span style="padding:4px 10px; border-radius:12px; font-size:12px; font-weight:600; {badge_style}">
#                         {status_label}
#                     </span>
#                 </td>
#                 <td style="padding:12px; font-weight:500; color:{'#16a34a' if last_dt else '#94a3b8'};">{last_str}</td>
#             </tr>
#         """

#     # Table 2: Food logs with photos and JSON preview
#     page_html += """
#         </table>

#         <h2>Logged Meals & Drinks</h2>
#         <table id="mealsTable">
#             <tr>
#                 <th>Phone Number</th>
#                 <th>Timestamp</th>
#                 <th>Note / Caption</th>
#                 <th>Photo</th>
#                 <th>Gemini Analysis</th>
#             </tr>
#     """

#     for phone, ts, caption, img_path in logs:
#         img_tag = "Text Only"
#         json_cell = "<span style='color:#94a3b8;'>No photo</span>"

#         if img_path and img_path != "text_only":
#             img_filename = os.path.basename(img_path)
#             img_tag = f"<a href='/view-images/{img_filename}' target='_blank'><img src='/view-images/{img_filename}' width='100' height='100' /></a>"

#             # Locate companion analysis JSON
#             base_name, _ = os.path.splitext(img_path)
#             json_path = f"{base_name}_analysis.json"

#             if os.path.exists(json_path):
#                 try:
#                     with open(json_path, "r", encoding="utf-8") as f:
#                         parsed_data = json.load(f)
#                     pretty_json = html_escape.escape(json.dumps(parsed_data, indent=2))
#                     json_cell = f"""
#                     <details>
#                         <summary>View JSON</summary>
#                         <pre class="json-box">{pretty_json}</pre>
#                     </details>
#                     """
#                 except Exception as e:
#                     json_cell = f"<span style='color:#ef4444;'>Error reading JSON: {html_escape.escape(str(e))}</span>"
#             else:
#                 json_cell = (
#                     "<span style='color:#f59e0b; font-size:12px;'>Analysis"
#                     " pending</span>"
#                 )

#         log_dt = parse_dt(ts)
#         log_str = log_dt.strftime("%Y-%m-%d %H:%M:%S") if log_dt else str(ts)
#         note_str = caption or ""

#         page_html += f"""
#             <tr style="border-bottom: 1px solid #e2e8f0;">
#                 <td style="padding:12px; font-family:monospace;">{phone}</td>
#                 <td style="padding:12px; color:#475569;">{log_str}</td>
#                 <td style="padding:12px;">{note_str}</td>
#                 <td style="padding:12px;">{img_tag}</td>
#                 <td style="padding:12px; width:350px;">{json_cell}</td>
#             </tr>
#         """

#     page_html += """
#         </table>

#         <script>
#         function filterByPhone() {
#             var input = document.getElementById("phoneSearch");
#             var filter = input.value.trim().toLowerCase();
#             var tables = ["participantsTable", "mealsTable"];

#             tables.forEach(function(tableId) {
#                 var table = document.getElementById(tableId);
#                 if (!table) return;
#                 var tr = table.getElementsByTagName("tr");
#                 for (var i = 1; i < tr.length; i++) {
#                     var tdPhone = tr[i].getElementsByTagName("td")[0];
#                     if (tdPhone) {
#                         var phoneText = tdPhone.textContent || tdPhone.innerText;
#                         if (phoneText.toLowerCase().indexOf(filter) > -1) {
#                             tr[i].style.display = "";
#                         } else {
#                             tr[i].style.display = "none";
#                         }
#                     }
#                 }
#             });
#         }
#         </script>

#     </body>
#     </html>
#     """
#     return page_html


@app.get("/admin/dashboard", response_class=HTMLResponse)
def view_dashboard(
    request: Request,
    phone_filter: str = "ALL",
    day_filter: str = "ALL",
    meal_filter: str = "ALL",
):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    now = datetime.now()
    today_date = now.date()
    cutoff_24h = now - timedelta(hours=24)

    # -------------------------------------------------------------
    # 1. Fetch participants, day 1 anchor, and last interaction
    # -------------------------------------------------------------
    c.execute(
        """
        SELECT 
            u.phone_number,
            u.start_timestamp,
            u.status,
            MIN(m.timestamp) AS first_interaction,
            MAX(m.timestamp) AS last_interaction
        FROM users u
        LEFT JOIN test_meal_logs m ON u.phone_number = m.phone_number
        GROUP BY u.phone_number
        ORDER BY last_interaction DESC
    """
    )
    users = c.fetchall()

    # Build user starts map for calculating day in meal logs
    user_starts = {}
    for u_phone, start_ts, _, first_int, _ in users:
        if first_int:
            try:
                user_starts[u_phone] = datetime.fromisoformat(str(first_int)).date()
            except Exception:
                pass
        if u_phone not in user_starts and start_ts:
            try:
                user_starts[u_phone] = datetime.fromtimestamp(float(start_ts)).date()
            except Exception:
                user_starts[u_phone] = today_date

    # -------------------------------------------------------------
    # 2. Fetch distinct phone numbers for the filter dropdown
    # -------------------------------------------------------------
    c.execute("SELECT DISTINCT phone_number FROM test_meal_logs ORDER BY phone_number")
    all_phones = [row[0] for row in c.fetchall()]

    # -------------------------------------------------------------
    # 3. Fetch all meal logs
    # -------------------------------------------------------------
    c.execute(
        "SELECT id, phone_number, timestamp, caption, image_path, meal_type FROM"
        " test_meal_logs ORDER BY timestamp DESC"
    )
    raw_meals = c.fetchall()
    conn.close()

    # -------------------------------------------------------------
    # Helper to parse dates safely
    # -------------------------------------------------------------
    def parse_dt(val):
        if not val:
            return None
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val)
        if isinstance(val, str):
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    return datetime.strptime(val[:19], fmt)
                except ValueError:
                    pass
        return None

    # -------------------------------------------------------------
    # Build Table 1 Rows (Participants)
    # -------------------------------------------------------------
    participant_rows = []
    for phone, start_ts, db_status, first_int, last_int in users:
        reg_dt = parse_dt(start_ts)
        first_dt = parse_dt(first_int)
        last_dt = parse_dt(last_int)

        reg_str = reg_dt.strftime("%Y-%m-%d %H:%M:%S") if reg_dt else "N/A"
        last_str = last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else "Never logged"

        latest_activity = last_dt or reg_dt
        is_inactive = bool(latest_activity and latest_activity < cutoff_24h)

        if is_inactive:
            status_label = "inactive"
            badge_style = "background:#fee2e2; color:#ef4444; border:1px solid #fca5a5;"
        else:
            status_label = "active"
            badge_style = "background:#dcfce7; color:#16a34a; border:1px solid #86efac;"

        if first_dt:
            anchor_date = last_dt.date() if (is_inactive and last_dt) else today_date
            day_num = (anchor_date - first_dt.date()).days + 1

            if day_num > 15:
                day_badge = (
                    f"<span style='color:#64748b; font-weight:600;'>Completed Day"
                    f" {day_num}</span>"
                )
            elif is_inactive:
                day_badge = (
                    f"<span style='color:#ef4444; font-weight:700;'>Paused at Day"
                    f" {day_num}</span>"
                )
            else:
                day_badge = f"<span style='color:#2563eb; font-weight:700;'>Day {day_num}</span>"
        else:
            day_badge = "<span style='color:#94a3b8;'>Not started</span>"

        participant_rows.append(
            f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding:12px; font-family:monospace;">{phone}</td>
                <td style="padding:12px; color:#475569;">{reg_str}</td>
                <td style="padding:12px;">{day_badge}</td>
                <td style="padding:12px;">
                    <span style="padding:4px 10px; border-radius:12px; font-size:12px; font-weight:600; {badge_style}">
                        {status_label}
                    </span>
                </td>
                <td style="padding:12px; font-weight:500; color:{'#16a34a' if last_dt else '#94a3b8'};">{last_str}</td>
            </tr>
        """
        )

    # -------------------------------------------------------------
    # Build Table 2 Rows (Meals)
    # -------------------------------------------------------------
    meal_rows = []
    meal_options = ["Breakfast", "Lunch", "Snacks", "Dinner"]

    for row in raw_meals:
        m_id, phone, ts_str, caption, img_path, saved_type = row

        # Calculate Study Day
        try:
            log_dt = datetime.fromisoformat(str(ts_str))
            reg_date = user_starts.get(phone, log_dt.date())
            calc_day = (log_dt.date() - reg_date).days + 1
            calc_day = max(1, calc_day)
            day_label = f"Day {calc_day}"
        except Exception:
            calc_day = 1
            day_label = "Day 1"

        current_meal_type = saved_type or get_default_meal_type(ts_str)

        # Filter logic
        if phone_filter != "ALL" and phone != phone_filter:
            continue
        if day_filter != "ALL" and str(calc_day) != str(day_filter).replace("Day ", ""):
            continue
        if meal_filter != "ALL" and current_meal_type.lower() != meal_filter.lower():
            continue

        # Build Meal Type Dropdown
        dropdown_opts = "".join(
            [
                f"<option value='{opt}' {'selected' if opt.lower() == current_meal_type.lower() else ''}>{opt}</option>"
                for opt in meal_options
            ]
        )
        meal_type_select = f"""
            <select class="type-select" onchange="saveMealType({m_id}, this)">
                {dropdown_opts}
            </select>
        """

        # Image Cell
        if img_path and img_path != "text_only" and os.path.exists(img_path):
            img_name = os.path.basename(img_path)
            img_html = f"<a href='/view-images/{img_name}' target='_blank'><img src='/view-images/{img_name}' style='width:60px; height:60px; object-fit:cover; border-radius:6px; border:1px solid #cbd5e1;'></a>"
        else:
            img_html = "<span style='color:#94a3b8;'>Text Only</span>"

        # JSON Analysis Cell
        json_path = (
            f"{os.path.splitext(img_path)[0]}_analysis.json"
            if (img_path and img_path != "text_only")
            else ""
        )
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as jf:
                    parsed_data = json.load(jf)
                pretty_json = html_escape.escape(json.dumps(parsed_data, indent=2))
                json_cell = f"""
                    <details>
                        <summary style="cursor:pointer; color:#2563eb; font-weight:600; font-size:13px;">▶ View JSON</summary>
                        <pre class="json-box">{pretty_json}</pre>
                    </details>
                """
            except Exception as err:
                json_cell = f"<span style='color:#ef4444;'>Error: {html_escape.escape(str(err))}</span>"
        else:
            json_cell = (
                "<span style='color:#d97706; font-style:italic;'>Analysis"
                " pending</span>"
            )

        meal_rows.append(
            f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding:12px; font-family:monospace;">{phone}</td>
                <td style="padding:12px;"><span style="background:#e0f2fe; color:#0369a1; padding:3px 8px; border-radius:12px; font-weight:700; font-size:12px;">{day_label}</span></td>
                <td style="padding:12px;">{meal_type_select}</td>
                <td style="padding:12px; color:#64748b; font-size:13px;">{ts_str}</td>
                <td style="padding:12px;">{html_escape.escape(caption or '')}</td>
                <td style="padding:12px;">{img_html}</td>
                <td style="padding:12px;">{json_cell}</td>
            </tr>
        """
        )

    # Filter dropdown options
    phone_select_html = "".join(
        [
            f"<option value='{p}' {'selected' if phone_filter == p else ''}>{p}</option>"
            for p in all_phones
        ]
    )
    day_select_html = "".join(
        [
            f"<option value='{i}' {'selected' if day_filter == str(i) else ''}>Day {i}</option>"
            for i in range(1, 16)
        ]
    )
    meal_select_html = "".join(
        [
            f"<option value='{m}' {'selected' if meal_filter == m else ''}>{m}</option>"
            for m in meal_options
        ]
    )

    # -------------------------------------------------------------
    # Complete Page HTML
    # -------------------------------------------------------------
    page_html = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Dietary Study Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 24px; background: #f8fafc; color: #1e293b; }}
            h2 {{ margin-top: 32px; color: #0f172a; }}
            table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }}
            th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 14px; vertical-align: middle; }}
            th {{ background: #0f172a; color: white; }}
            .filters {{ display: flex; gap: 14px; margin-bottom: 20px; align-items: center; background: white; padding: 14px 18px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
            .filters label {{ font-size: 13px; font-weight: 600; color: #475569; }}
            .filters select {{ padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; background: white; }}
            .filters button {{ background: #0f172a; color: white; border: none; padding: 7px 14px; border-radius: 4px; font-size: 13px; cursor: pointer; }}
            .filters a {{ color: #64748b; font-size: 13px; text-decoration: none; margin-left: 6px; }}
            .type-select {{ padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; background: white; cursor: pointer; }}
            pre.json-box {{ background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px; font-size: 11px; white-space: pre-wrap; word-break: break-word; max-height: 250px; overflow-y: auto; margin-top: 8px; }}
            .search-box {{ width: 100%; max-width: 400px; padding: 10px 14px; margin-bottom: 20px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; outline: none; }}
        </style>
        <script>
            function filterByPhone() {{
                var input = document.getElementById("phoneSearch");
                var filter = input.value.toUpperCase();
                var table = document.getElementById("participantsTable");
                var tr = table.getElementsByTagName("tr");
                for (var i = 1; i < tr.length; i++) {{
                    var td = tr[i].getElementsByTagName("td")[0];
                    if (td) {{
                        var txtValue = td.textContent || td.innerText;
                        tr[i].style.display = txtValue.toUpperCase().indexOf(filter) > -1 ? "" : "none";
                    }}
                }}
            }}

            async function saveMealType(mealId, selectElement) {{
                selectElement.style.borderColor = "#2563eb";
                try {{
                    const res = await fetch('/admin/update-meal-type', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ meal_log_id: mealId, meal_type: selectElement.value }})
                    }});
                    if (res.ok) {{
                        selectElement.style.borderColor = "#22c55e";
                        setTimeout(() => selectElement.style.borderColor = "#cbd5e1", 1500);
                    }} else {{
                        alert('Could not update meal type.');
                        selectElement.style.borderColor = "#ef4444";
                    }}
                }} catch (e) {{
                    alert('Network error updating meal type: ' + e);
                    selectElement.style.borderColor = "#ef4444";
                }}
            }}
        </script>
    </head>
    <body>
        <h2>Registered Participants</h2>
        <input type="text" id="phoneSearch" class="search-box" placeholder="Search by phone number..." onkeyup="filterByPhone()" />
        <table id="participantsTable">
            <thead>
                <tr>
                    <th>Phone Number</th>
                    <th>Registered At</th>
                    <th>Study Day</th>
                    <th>Status</th>
                    <th>Last Interaction</th>
                </tr>
            </thead>
            <tbody>
                {''.join(participant_rows)}
            </tbody>
        </table>

        <h2>Logged Meals & Drinks</h2>
        <form method="get" action="/admin/dashboard" class="filters">
            <label>Phone:
                <select name="phone_filter">
                    <option value="ALL">All Participants</option>
                    {phone_select_html}
                </select>
            </label>

            <label>Day:
                <select name="day_filter">
                    <option value="ALL">All Days</option>
                    {day_select_html}
                </select>
            </label>

            <label>Meal Type:
                <select name="meal_filter">
                    <option value="ALL">All Types</option>
                    {meal_select_html}
                </select>
            </label>

            <button type="submit">Apply Filter</button>
            <a href="/admin/dashboard">Reset</a>
        </form>
        
        <table id="mealsTable">
            <thead>
                <tr>
                    <th>Phone Number</th>
                    <th>Day</th>
                    <th>Meal Type</th>
                    <th>Timestamp</th>
                    <th>Note / Caption</th>
                    <th>Photo</th>
                    <th>Analysis</th>
                </tr>
            </thead>
            <tbody>
                {''.join(meal_rows)}
            </tbody>
        </table>
    </body>
    </html>"""

    return HTMLResponse(page_html)


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
        """
        CREATE TABLE IF NOT EXISTS test_meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            caption TEXT,
            image_path TEXT
        )
    """
    )

    try:
        c.execute("ALTER TABLE test_meal_logs ADD COLUMN meal_type TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists, safe to ignore

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
    raw_json TEXT,
    FOREIGN KEY (meal_log_id) REFERENCES test_meal_logs(id),
    FOREIGN KEY (phone_number) REFERENCES users(phone_number)
    )
    """
    )

    conn.commit()
    conn.close()


init_db()


# 2. Worker to download media, save to disk, record in DB, and reply
def process_incoming_meal(media_id: str, sender: str, caption: str):
    conn = None
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

        image = Image.open(io.BytesIO(img_response.content))
        image = image.convert("RGB")
        image.thumbnail((1024, 1024))  # keeps aspect ratio, shrinks max edge
        image.save(filename, "JPEG", optimize=True, quality=75)

        # 2. Connect and execute
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO test_meal_logs (phone_number, timestamp, caption, image_path) VALUES (?, ?, ?, ?)",
            (sender, datetime.now(), caption, filename),
        )
        conn.commit()
        meal_log_id = c.lastrowid

        # D. Send WhatsApp confirmation reply
        ack_endpoint = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": sender,
            "type": "text",
            "text": {"body": "Logged! 📸 Meal recorded."},
        }
        requests.post(ack_endpoint, headers=headers, json=payload)

        # --- GEMINI PROCESSING TEST ---
        print(f"[Test] Sending {filename} to Gemini...")
        try:
            # Run the analysis
            gemini_output = run_gemini_vision_pipeline(filename, caption)

            # 1. Print directly to Railway Logs so you can see it live
            print(
                f"--- GEMINI ANALYSIS SUCCESS ---\n{json.dumps(gemini_output, indent=2)}"
            )

            # 2. Save to a local JSON file in your persistent volume
            base_name, _ = os.path.splitext(filename)
            output_filepath = f"{base_name}_analysis.json"
            with open(output_filepath, "w", encoding="utf-8") as json_file:
                json.dump(gemini_output, json_file, indent=2, ensure_ascii=False)

            if conn and meal_log_id:
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
                        json.dumps(gemini_output.get("identified_items", [])),
                        gemini_output.get("meal_type"),
                        gemini_output.get("food_source_type"),
                        gemini_output.get("staple_format"),
                        gemini_output.get("estimated_protein_grams", 0.0),
                        gemini_output.get("estimated_carbs_grams", 0.0),
                        gemini_output.get("estimated_fat_grams", 0.0),
                        gemini_output.get("estimated_fiber_grams", 0.0),
                        gemini_output.get("protein_source_present", False),
                        gemini_output.get("protein_source_type"),
                        gemini_output.get("is_caffeine_or_sugar_crutch", False),
                        gemini_output.get("primary_fuel_source"),
                        gemini_output.get("crash_risk_level"),
                        json.dumps(gemini_output),
                    ),
                )
                conn.commit()

        except Exception as e:
            print(f"--- GEMINI PROCESSING FAILED ---\n{e}")

        # C. Insert into SQLite
        # conn = sqlite3.connect(DB_FILE)
        # c = conn.cursor()
        # c.execute(
        #     "INSERT INTO test_meal_logs (phone_number, timestamp, caption, image_path) VALUES (?, ?, ?, ?)",
        #     (sender, datetime.now(), caption, filename),
        # )
        # conn.commit()
        # conn.close()
        # print(f"[Success] Saved meal from {sender} -> {filename}")

    except Exception as e:
        print(f"[Exception] Failed processing message from {sender}: {e}")

    finally:
        if conn:
            conn.close()


def get_default_meal_type(timestamp_str: str) -> str:
    """Categorises meal by time:

    07:00 - 11:30 -> Breakfast
    11:30 - 15:00 -> Lunch
    15:00 - 19:00 -> Snacks
    19:00 - 07:00 -> Dinner
    """
    try:
        if isinstance(timestamp_val, str):
            dt = datetime.fromisoformat(timestamp_val)
        elif isinstance(timestamp_val, (int, float)):
            dt = datetime.fromtimestamp(timestamp_val)
        else:
            dt = timestamp_val
    except Exception:
        dt = datetime.now()

    t = dt.time()
    if time(7, 0) <= t < time(11, 30):
        return "Breakfast"
    elif time(11, 30) <= t < time(15, 0):
        return "Lunch"
    elif time(15, 0) <= t < time(19, 0):
        return "Snacks"
    else:
        return "Dinner"


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
