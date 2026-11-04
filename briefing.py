"""
Daily briefing: din ka pehla app kholne par, ya user ke maangne par. Aaj ke reminders aur
scheduled messages, mausam, aur WhatsApp ka khulasa.
"""

import asyncio
import os
import sqlite3
from datetime import datetime

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from reminders import todays_reminders
from scheduled import todays_scheduled
from whatsapp_summary import make_summary

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "briefing.db")
FIRST_HOUR = 5  # raat ko app khole to subah ka briefing na aaye
WHATSAPP_HOURS = 12

_lock = asyncio.Lock()  # do tab ek saath khulen to model do dafa na chale


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS briefing (day TEXT PRIMARY KEY, text TEXT, shown INTEGER DEFAULT 0)")
    return conn


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _save(text, shown):
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM briefing")  # sirf aaj ka chahiye, is me WhatsApp ka data hai
        conn.execute("INSERT INTO briefing (day, text, shown) VALUES (?, ?, ?)", (_today(), text, shown))
    conn.close()


def _plans():
    lines = [f"- {r['remind_at'][11:]}: {r['text']}" for r in todays_reminders()]
    lines += [f"- {s['time']}: {s['to']} ko message: {s['message']}" for s in todays_scheduled()]
    return "\n".join(lines) or "Aaj ka koi reminder ya scheduled message nahi."


async def _weather():
    city = os.environ.get("BRIEFING_CITY", "").strip()
    if not city:
        return None
    try:
        result = await TavilySearch(max_results=1, include_answer=True).ainvoke(
            {"query": f"current weather today in {city}, temperature and rain"}
        )
        return result.get("answer") or f"{city} ka mausam nahi mila."
    except Exception as e:
        print(f"[briefing/error] {type(e).__name__}: {e}")
        return f"{city} ka mausam abhi nahi mil saka."


async def _whatsapp():
    # Limit khatm ho to baqi briefing phir bhi aaye
    try:
        return await make_summary("", WHATSAPP_HOURS)
    except Exception as e:
        print(f"[briefing/error] {type(e).__name__}: {e}")
        return "WhatsApp ka khulasa abhi nahi ban saka."


async def _build():
    weather, whatsapp = await asyncio.gather(_weather(), _whatsapp())
    parts = [f"☀️ Aaj ka briefing: {datetime.now().strftime('%A, %d %B')}", f"📋 Aaj ke kaam:\n{_plans()}"]
    if weather:
        parts.append(f"🌤️ Mausam: {weather}")
    parts.append(f"💬 WhatsApp (pichle {WHATSAPP_HOURS} ghante):\n{whatsapp}")
    return "\n\n".join(parts)


async def first_briefing():
    """Aaj ka briefing agar abhi tak dikhaya nahi gaya, warna khali."""
    if datetime.now().hour < FIRST_HOUR:
        return ""
    async with _lock:
        conn = _connect()
        row = conn.execute("SELECT text, shown FROM briefing WHERE day=?", (_today(),)).fetchone()
        conn.close()
        if row:
            return "" if row[1] else row[0]
        text = await _build()
        _save(text, 0)
        return text


def mark_briefing_shown():
    conn = _connect()
    with conn:
        conn.execute("UPDATE briefing SET shown=1 WHERE day=?", (_today(),))
    conn.close()


@tool
async def daily_briefing() -> str:
    """Aaj ka briefing: reminders, scheduled messages, mausam aur WhatsApp ka khulasa. Jab user
    briefing maange ya poochhe "aaj ka din kaisa hai". Jawab badle baghair user ko do."""
    async with _lock:
        text = await _build()
        _save(text, 1)  # maang kar le liya to app kholne par dobara na aaye
    return text
