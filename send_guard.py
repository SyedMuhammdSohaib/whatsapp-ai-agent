"""
Bhejne ki rok: model send tool chalaye to kuch nahi jata, tool call yahan ruk jati hai.
Message tabhi jata hai jab user ka apna "haan" answer_pending tak pahunche, jo model
ke zariye nahi guzarta. Isi liye WhatsApp message me likhi koi hidayat bhi kuch bhej nahi sakti.
"""

import json
import re
import time

from contacts import _load_contacts
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.config import get_config
from whatsapp_summary import _canonical, _lid_map, _name

SEND_TOOLS = {"send_message", "send_file", "send_audio_message"}
HOLD_SECONDS = 600  # itni der baad "haan" purane message par na lage

YES = {
    "haan", "han", "ha", "haan ji", "ji haan", "ji", "yes", "send", "ok", "theek hai",
    "haan bhej do", "han bhej do", "bhej do", "haan bhejo", "bhejo",
    "ہاں", "جی", "جی ہاں", "ہاں جی", "بھیج دو", "ہاں بھیج دو", "ٹھیک ہے",
}
NO = {"nahi", "nhi", "nahin", "no", "cancel", "mat bhejo", "rehne do", "نہیں", "مت بھیجو", "رہنے دو"}

_pending = {}


def _normalize(text):
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _label(recipient):
    # Confirmation me naam aur number dono, asli recipient ke mutabiq
    try:
        jid = recipient if "@" in recipient else f"{recipient}@s.whatsapp.net"
        canonical = _canonical(jid, _lid_map())
        name = _name(canonical, _load_contacts())
    except Exception:
        return recipient
    return recipient if name in recipient else f"{name} ({recipient})"


def _describe(args):
    body = f"Message: {args['message']}" if "message" in args else f"File: {args.get('media_path', '')}"
    return f"Kisko: {_label(str(args.get('recipient', '')))}\n{body}"


def _outcome(result):
    # (kamyab hua?, tafseel); pata na chale to None
    artifact = result.artifact if isinstance(result.artifact, dict) else {}
    data = artifact.get("structured_content")
    content = result.content
    if isinstance(content, list):
        content = " ".join(b if isinstance(b, str) else b.get("text", "") for b in content)
    if not isinstance(data, dict):
        try:
            data = json.loads(content)
        except (TypeError, ValueError):
            data = {}
    if isinstance(data, dict) and "success" in data:
        return bool(data["success"]), str(data.get("message", ""))
    return None, str(content)


@wrap_tool_call
async def hold_for_approval(request, handler):
    call = request.tool_call
    if call["name"] not in SEND_TOOLS:
        return await handler(request)
    thread_id = get_config()["configurable"]["thread_id"]
    held = _pending.setdefault(thread_id, {"since": time.time(), "calls": []})
    held["calls"].append({"tool": request.tool, "name": call["name"], "args": call["args"]})
    return ToolMessage(
        "Abhi kuch NAHI bheja gaya. System user se confirm karwa raha hai. "
        "Mat kaho ke bhej diya, aur dobara ye tool mat chalao.",
        tool_call_id=call["id"],
    )


def pending_prompt(thread_id):
    # Model ke jawab ki jagah yahi dikhao, taake user wahi dekhe jo asal me jayega
    held = _pending.get(thread_id)
    if not held:
        return None
    parts = "\n\n".join(_describe(c["args"]) for c in held["calls"])
    return f"Ye bhejun?\n\n{parts}\n\nHaan ya nahi?"


async def _send(call):
    try:
        result = await call["tool"].ainvoke(
            {"type": "tool_call", "name": call["name"], "args": call["args"], "id": "user-approved"}
        )
        success, detail = _outcome(result)
    except Exception as e:
        success, detail = False, f"{type(e).__name__}: {e}"
    who = _label(str(call["args"].get("recipient", "")))
    if success:
        return f"✅ {who} ko bhej diya."
    if success is None:
        return f"⚠️ {who} ko bhejne ka pata nahi chala, WhatsApp me dekh lein. {detail}"
    return f"❌ {who} ko nahi gaya: {detail}"


async def answer_pending(agent, config, text):
    """User ka jawab ruke hue message par lagao. (seedha jawab, ya None aur note) deta hai.
    Haan ya nahi ke ilawa kuch bhi kaha to message cancel, taake purana "haan" kabhi na lage."""
    held = _pending.pop(config["configurable"]["thread_id"], None)
    if not held:
        return None, ""
    answer = _normalize(text)
    expired = time.time() - held["since"] > HOLD_SECONDS
    if answer in YES and not expired:
        reply = "\n".join([await _send(call) for call in held["calls"]])
    elif answer in NO or answer in YES:
        reply = "Theek hai, nahi bheja." if not expired else "Der ho gayi thi, is liye nahi bheja. Dobara kahein."
    else:
        return None, "(Pichla message nahi bheja gaya.)\n"
    # Agent ko bhi pata rahe ke kya hua
    await agent.aupdate_state(config, {"messages": [AIMessage(reply)]})
    return reply, ""
