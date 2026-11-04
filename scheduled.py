"""
Scheduled messages: user ki "haan" ke baad message database me save hota hai, aur backend
waqt aane par khud bhejta hai. Backend restart hone par bhi yaad rehta hai.
"""

import asyncio
import os
import sqlite3
from datetime import datetime, timedelta

from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from send_guard import TIME_FORMAT, _label, _outcome, describe_time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduled.db")
CHECK_SECONDS = 20
LATE_LIMIT = timedelta(hours=1)  # itna late ho gaya to mat bhejo: raat ko "good morning" na jaye

_task = None


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scheduled ("
        "id INTEGER PRIMARY KEY, recipient TEXT, message TEXT, send_at TEXT, "
        "status TEXT DEFAULT 'pending', detail TEXT DEFAULT '', notified INTEGER DEFAULT 1)"
    )
    return conn


def _time_error(send_at):
    try:
        when = datetime.strptime(send_at, TIME_FORMAT)
    except (TypeError, ValueError):
        return f"Abhi kuch schedule NAHI hua: waqt '{send_at}' is format me do: YYYY-MM-DD HH:MM."
    if when <= datetime.now():
        return f"Abhi kuch schedule NAHI hua: {describe_time(send_at)} guzar chuka hai. User se naya waqt poocho."
    return None


def _finish(conn, row_id, status, detail=""):
    # notified=0: agli chat me user ko batana hai
    conn.execute("UPDATE scheduled SET status=?, detail=?, notified=0 WHERE id=?", (status, detail, row_id))
    conn.commit()


async def _send_due(send_tool):
    with _connect() as conn:
        now = datetime.now()
        rows = conn.execute("SELECT * FROM scheduled WHERE status='pending'").fetchall()
        for row in rows:
            when = datetime.strptime(row["send_at"], TIME_FORMAT)
            if when > now:
                continue
            if now - when > LATE_LIMIT:
                _finish(conn, row["id"], "failed" if row["detail"] else "missed", row["detail"])
                continue
            # Pehle claim karo: do dafa kabhi na jaye, chahe yahan crash ho jaye
            claimed = conn.execute(
                "UPDATE scheduled SET status='sending' WHERE id=? AND status='pending'", (row["id"],)
            ).rowcount
            conn.commit()
            if not claimed:
                continue
            try:
                result = await send_tool.ainvoke(
                    {
                        "type": "tool_call",
                        "name": send_tool.name,
                        "args": {"recipient": row["recipient"], "message": row["message"]},
                        "id": f"scheduled-{row['id']}",
                    }
                )
                success, detail = _outcome(result)
            except Exception as e:
                success, detail = None, f"{type(e).__name__}: {e}"
            if success:
                _finish(conn, row["id"], "sent")
            elif success is None:
                # Pata nahi gaya ya nahi, dobara bheja to do dafa ja sakta hai
                _finish(conn, row["id"], "unknown", detail)
            else:
                # Saaf "nahi gaya" (jaise bridge band), agle chakkar me phir koshish
                conn.execute("UPDATE scheduled SET status='pending', detail=? WHERE id=?", (detail, row["id"]))
                conn.commit()


async def _loop(send_tool):
    while True:
        try:
            await _send_due(send_tool)
        except Exception as e:
            print(f"[schedule/error] {type(e).__name__}: {e}")
        await asyncio.sleep(CHECK_SECONDS)


def start_scheduler(send_tool):
    global _task
    with _connect() as conn:
        # Pichli dafa bhejte waqt band hua to pata nahi gaya ya nahi
        for row in conn.execute("SELECT id FROM scheduled WHERE status='sending'").fetchall():
            _finish(conn, row["id"], "unknown", "Backend bhejte waqt band ho gaya tha.")
    _task = asyncio.create_task(_loop(send_tool))
    return _task


def take_notices():
    """Jo scheduled messages nipat gaye, unki khabar (chat ke jawab ke shuru me)."""
    words = {
        "sent": "✅ bhej diya",
        "missed": "⚠️ nahi gaya, us waqt backend band tha aur ab bahut der ho gayi",
        "failed": "❌ nahi gaya",
        "unknown": "⚠️ pata nahi chala gaya ya nahi, WhatsApp me dekh lein",
    }
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM scheduled WHERE notified=0").fetchall()
        conn.execute("UPDATE scheduled SET notified=1 WHERE notified=0")
    lines = [
        f"⏰ {_label(r['recipient'])} ({describe_time(r['send_at'])}): {words[r['status']]}"
        + (f" - {r['detail']}" if r["detail"] and r["status"] != "sent" else "")
        for r in rows
    ]
    return "\n".join(lines) + "\n\n" if lines else ""


def todays_scheduled():
    today = datetime.now().strftime("%Y-%m-%d")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled WHERE status='pending' AND send_at LIKE ? ORDER BY send_at", (f"{today}%",)
        ).fetchall()
    return [{"time": r["send_at"][11:], "to": _label(r["recipient"]), "message": r["message"]} for r in rows]


@wrap_model_call
async def tell_current_time(request, handler):
    # Model ko aaj ki tareekh pata nahi hoti, "kal 9 baje" ke liye chahiye
    now = datetime.now().strftime("%A, " + TIME_FORMAT)
    system = request.system_message.content if request.system_message else ""
    return await handler(request.override(system_message=SystemMessage(f"{system}\nAbhi ka waqt: {now}")))


@tool
def schedule_message(recipient: str, message: str, send_at: str) -> dict:
    """WhatsApp message baad me kisi waqt bhejne ke liye rakho, jaise "kal subah 9 baje".
    send_at: 'YYYY-MM-DD HH:MM' (24 ghante wala, abhi ke waqt ke hisab se). Recipient naam se
    ho to pehle find_contact chalao. Waqt saaf na ho to user se poocho, khud andaza mat lagao."""
    error = _time_error(send_at)
    if error:
        return {"success": False, "message": error}
    with _connect() as conn:
        conn.execute(
            "INSERT INTO scheduled (recipient, message, send_at) VALUES (?, ?, ?)",
            (recipient, message, send_at),
        )
    return {"success": True, "message": "Scheduled."}


# Hold karne se pehle hi waqt check ho, taake ghalat waqt par "haan" na maangi jaye
schedule_message.metadata = {"validate": lambda args: _time_error(args.get("send_at"))}


@tool
def list_scheduled_messages() -> str:
    """Jo scheduled messages abhi bheje jaane baqi hain, unki list id ke saath."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM scheduled WHERE status='pending' ORDER BY send_at").fetchall()
    if not rows:
        return "Koi scheduled message baqi nahi."
    return "\n".join(
        f"- id {r['id']}: {_label(r['recipient'])}, {describe_time(r['send_at'])}: {r['message']}" for r in rows
    )


@tool
def cancel_scheduled_message(id: int) -> str:
    """Scheduled message cancel karo. id list_scheduled_messages se lo."""
    with _connect() as conn:
        cancelled = conn.execute("DELETE FROM scheduled WHERE id=? AND status='pending'", (id,)).rowcount
    return "Cancel ho gaya." if cancelled else f"id {id} ka koi baqi message nahi mila."


SCHEDULE_TOOLS = [schedule_message, list_scheduled_messages, cancel_scheduled_message]
