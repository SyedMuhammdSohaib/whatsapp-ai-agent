"""
Reminders: waqt aane par web app user ko chat me dikhata aur bol kar batata hai.
Ye WhatsApp par kuch nahi bhejte. Backend ya browser band ho to khulne par dikh jate hain.
"""

import os
import sqlite3
from datetime import datetime

from langchain_core.tools import tool
from scheduled import _time_error
from send_guard import TIME_FORMAT, describe_time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminders.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, text TEXT, remind_at TEXT, shown INTEGER DEFAULT 0)"
    )
    return conn


def due_reminders():
    now = datetime.now().strftime(TIME_FORMAT)
    # Is format me text compare aur waqt compare ek hi baat hai
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM reminders WHERE shown=0 AND remind_at<=? ORDER BY remind_at", (now,)).fetchall()
    return [
        {"id": r["id"], "text": f"⏰ Yaad dihani: {r['text']}" + ("" if r["remind_at"] == now else f" ({describe_time(r['remind_at'])} ka waqt tha)")}
        for r in rows
    ]


def todays_reminders():
    today = datetime.now().strftime("%Y-%m-%d")
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM reminders WHERE shown=0 AND remind_at LIKE ? ORDER BY remind_at", (f"{today}%",)
        ).fetchall()


def mark_shown(ids):
    with _connect() as conn:
        conn.executemany("UPDATE reminders SET shown=1 WHERE id=?", [(i,) for i in ids])


@tool
def set_reminder(text: str, remind_at: str) -> str:
    """User ko khud kisi waqt yaad dilao, jaise "kal 9 baje yaad dilana". Ye WhatsApp par kisi ko
    nahi jata. remind_at: 'YYYY-MM-DD HH:MM' (24 ghante wala, abhi ke waqt ke hisab se).
    Waqt saaf na ho to user se poocho, khud andaza mat lagao."""
    error = _time_error(remind_at)
    if error:
        return error
    # "9:00" jaisa waqt bhi "09:00" ban kar save ho, warna due_reminders ka compare ghalat hoga
    remind_at = datetime.strptime(remind_at, TIME_FORMAT).strftime(TIME_FORMAT)
    with _connect() as conn:
        conn.execute("INSERT INTO reminders (text, remind_at) VALUES (?, ?)", (text, remind_at))
    return f"Reminder lag gaya: {describe_time(remind_at)}."


@tool
def list_reminders() -> str:
    """Jo reminders abhi baqi hain, unki list id ke saath."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM reminders WHERE shown=0 ORDER BY remind_at").fetchall()
    return "\n".join(f"- id {r['id']}: {describe_time(r['remind_at'])}: {r['text']}" for r in rows) or "Koi reminder baqi nahi."


@tool
def cancel_reminder(id: int) -> str:
    """Reminder cancel karo. id list_reminders se lo."""
    with _connect() as conn:
        cancelled = conn.execute("DELETE FROM reminders WHERE id=? AND shown=0", (id,)).rowcount
    return "Cancel ho gaya." if cancelled else f"id {id} ka koi baqi reminder nahi mila."


REMINDER_TOOLS = [set_reminder, list_reminders, cancel_reminder]
