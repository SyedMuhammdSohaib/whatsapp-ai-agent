import os
import sqlite3
from pathlib import Path

from langchain_core.tools import tool

# whatsapp-bridge apna data store/ folder me rakhta hai:
#   whatsapp.db -> phone me save kiye naam (whatsmeow_contacts)
#   messages.db -> chats aur unke naam
def _store_dir():
    server_dir = os.path.normpath(os.environ["WHATSAPP_MCP_PATH"])
    return os.path.join(os.path.dirname(server_dir), "whatsapp-bridge", "store")


def _connect(name):
    path = os.path.join(_store_dir(), name)
    if not os.path.exists(path):
        return None
    # Read-only, taake chalte hue bridge ke data ko na chheden.
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def _rows(conn, sql):
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []


def _load_contacts():
    """{jid: set(naam)} - dono databases se."""
    contacts = {}

    def add(jid, *names):
        if not jid:
            return
        bucket = contacts.setdefault(jid, set())
        bucket.update(n.strip() for n in names if n and n.strip() and not n.strip().isdigit())

    conn = _connect("whatsapp.db")
    if conn:
        with conn:
            # Naye WhatsApp accounts "@lid" JIDs dete hain; inhe asli number me badlo.
            lid_to_pn = {
                lid.split("@")[0]: pn.split("@")[0]
                for lid, pn in _rows(conn, "SELECT lid, pn FROM whatsmeow_lid_map")
            }
            for jid, first, full, push, business in _rows(
                conn,
                "SELECT their_jid, first_name, full_name, push_name, business_name "
                "FROM whatsmeow_contacts",
            ):
                user, _, server = jid.partition("@")
                if server == "lid" and user in lid_to_pn:
                    jid = f"{lid_to_pn[user]}@s.whatsapp.net"
                add(jid, first, full, push, business)
        conn.close()

    conn = _connect("messages.db")
    if conn:
        with conn:
            for jid, name in _rows(conn, "SELECT jid, name FROM chats"):
                add(jid, name)
        conn.close()

    return contacts


@tool
def find_contact(name: str) -> str:
    """Naam se WhatsApp contact ya group dhoondo (phone me save kiya naam,
    WhatsApp profile naam ya chat naam). Message bhejne se pehle isi se
    recipient nikalo. Result me har match ka naam aur recipient hota hai;
    send_message me wahi recipient do."""
    words = name.lower().split()
    if not words:
        return "Naam khali hai."

    contacts = _load_contacts()
    if not contacts:
        return f"Contacts database nahi mila ({_store_dir()}). Kya whatsapp-bridge chal raha hai?"

    matches = []
    for jid, names in contacts.items():
        text = " ".join(names).lower()
        score = sum(w in text for w in words)
        if score:
            matches.append((score, jid, names))

    if not matches:
        return f"'{name}' naam ka koi contact nahi mila."

    best = max(m[0] for m in matches)
    matches = sorted((m for m in matches if m[0] == best), key=lambda m: sorted(m[2]))[:10]
    lines = []
    for _, jid, names in matches:
        user, _, server = jid.partition("@")
        kind = "group" if server == "g.us" else "contact"
        number = f", number: {user}" if server == "s.whatsapp.net" else ""
        recipient = user if server == "s.whatsapp.net" else jid
        lines.append(f"- {' / '.join(sorted(names)) or user} ({kind}{number}) -> recipient: {recipient}")
    if best < len(words):
        lines.insert(0, f"Poora naam '{name}' nahi mila, milte-julte contacts:")
    return "\n".join(lines)
