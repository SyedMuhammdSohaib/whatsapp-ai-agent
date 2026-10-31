"""
FastAPI backend — WhatsApp AI Agent + realistic voice (edge-tts).
/chat   -> agent se baat
/tts    -> text ko realistic awaaz (mp3). Script detect karke Urdu/English voice chunti hai.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import edge_tts
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

load_dotenv()

MODEL = os.environ["MODEL"]
WHATSAPP_MCP_PATH = os.environ["WHATSAPP_MCP_PATH"]

# Realistic neural voices (free)
URDU_VOICE = "ur-PK-UzmaNeural"      # mard ke liye: ur-PK-AsadNeural
ENGLISH_VOICE = "en-US-AriaNeural"   # mard ke liye: en-US-GuyNeural

SYSTEM_PROMPT = (
    "Tum ek helpful WhatsApp assistant ho. "
    "Jab user Urdu me baat kare to jawab SAAF URDU SCRIPT (اردو) me do. "
    "Jab user English me baat kare to English me jawab do. "
    "Hindi ya Devanagari kabhi istemaal mat karo. "
    "Tumhare paas do tarah ke tools hain: WhatsApp (message bhejna/padhna) "
    "aur web search (tavily_search) - taaza ya real-time info ke liye. "
    "Jab user kisi nayi jaankari (mausam, rate, news, koi fact) ke baare me "
    "pooche, to pehle web search tool use karo, phir jawab do. "
    "Message bhejne se PEHLE user ko hamesha confirm karo. "
    "Jab user confirm kar de (haan / yes), to pichhle message ko bina dobara "
    "pooche send_message tool se bhej do. "
    "Tumhe baat-cheet yaad rehti hai, context use karo. Jawab hamesha CHHOTA aur seedha rakho (1-2 line), sirf zaroorat ho to lamba karo."
)

STATE = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = MultiServerMCPClient(
        {
            "whatsapp": {
                "command": "uv",
                "args": ["--directory", WHATSAPP_MCP_PATH, "run", "main.py"],
                "transport": "stdio",
            }
        }
    )
    wa_tools = await client.get_tools()
    keep = {"send_message", "search_contacts", "list_chats", "list_messages", "get_chat"}
    wa_tools = [t for t in wa_tools if t.name in keep]
    web = TavilySearch(max_results=1)
    tools = wa_tools + [web]
    model = init_chat_model(MODEL, max_retries=6, timeout=120)
    memory = MemorySaver()
    STATE["agent"] = create_react_agent(
        model, tools, prompt=SYSTEM_PROMPT, checkpointer=memory
    )
    print(f"[ok] Agent ready with {len(tools)} tools.")
    yield
    STATE.clear()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    message: str
    thread_id: str = "web-session"


class TTSIn(BaseModel):
    text: str
    voice: str = ""  # khaali = auto-detect


def _text(content):
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(str(c.get("text", "")))
            else:
                parts.append(str(c))
        return " ".join(p for p in parts if p).strip()
    return str(content)


def pick_voice(text):
    # Agar text me Urdu/Arabic script ho to Urdu voice, warna English
    for ch in text:
        if "؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ":
            return URDU_VOICE
    return ENGLISH_VOICE


@app.get("/")
def health():
    return {"status": "ok", "agent": "ready" if "agent" in STATE else "loading"}


@app.post("/chat")
async def chat(inp: ChatIn):
    agent = STATE.get("agent")
    if agent is None:
        return {"reply": "Agent abhi load ho raha hai, thodi der baad try karo."}
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": inp.message}]},
            config={"configurable": {"thread_id": inp.thread_id}},
        )
        return {"reply": _text(result["messages"][-1].content)}
    except Exception as e:
        return {"reply": f"[error] {type(e).__name__}: {e}"}


@app.post("/tts")
async def tts(inp: TTSIn):
    text = (inp.text or "").strip()
    if not text:
        return Response(status_code=204)
    voice = inp.voice or pick_voice(text)
    try:
        communicate = edge_tts.Communicate(text, voice)
        audio = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        return Response(content=str(e).encode(), status_code=500)
