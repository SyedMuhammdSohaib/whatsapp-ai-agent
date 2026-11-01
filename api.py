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
from agent import WebSearchInput, send_recent_history, tool_result_as_text
from contacts import find_contact
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import MemorySaver
from models import fallback_middleware, make_model
from youtube import YOUTUBE_TOOLS

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
    "YouTube ke liye: video ya gaana chalane ko play_youtube, rokne, chalane aur "
    "aage-peeche karne ko control_youtube, aur video ke andar kya hai ya use samjhane "
    "ko explain_youtube_video use karo. YouTube ke kaam ke liye confirm mat karo, foran karo "
    "(confirm sirf WhatsApp message ke liye hai). Ye kaam tool ke baghair kabhi mat bolo ke ho gaya. "
    "Chalti video ke baare me koi bhi sawal ho to pehle explain_youtube_video chalao, "
    "user se transcript ya naam mat maango. "
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
    web = TavilySearch(max_results=1, args_schema=WebSearchInput)
    tools = wa_tools + [web, find_contact] + YOUTUBE_TOOLS
    model = make_model(MODEL)
    memory = MemorySaver()
    # tool_result_as_text: khali tool result par Groq 400 deta hai, use text bana deta hai
    STATE["agent"] = create_agent(
        model,
        tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[send_recent_history, fallback_middleware(), tool_result_as_text],
        checkpointer=memory,
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
    video_id: str = ""  # player me abhi chalne wali video
    video_title: str = ""
    video_time: float = 0


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


def youtube_commands(messages):
    # Is sawal ke tool results me se player ke liye commands
    commands = []
    for m in reversed(messages):
        if m.type == "human":
            break
        artifact = getattr(m, "artifact", None)
        if isinstance(artifact, dict) and "youtube" in artifact:
            commands.insert(0, artifact["youtube"])
    return commands


@app.get("/")
def health():
    return {"status": "ok", "agent": "ready" if "agent" in STATE else "loading"}


@app.post("/chat")
async def chat(inp: ChatIn):
    agent = STATE.get("agent")
    if agent is None:
        return {"reply": "Agent abhi load ho raha hai, thodi der baad try karo."}
    message = inp.message
    if inp.video_id:
        # Taake "is video/gaane" ka matlab agent ko pata ho
        message = f"(Player me abhi chal rahi hai: {inp.video_title})\n{message}"
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": message}]},
            config={
                "configurable": {
                    "thread_id": inp.thread_id,
                    "video_id": inp.video_id,
                    "video_time": inp.video_time,
                }
            },
        )
        print(f"[model] {result['messages'][-1].response_metadata.get('model_name')}")
        return {
            "reply": _text(result["messages"][-1].content),
            "youtube": youtube_commands(result["messages"]),
        }
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
        if not audio:
            return Response(status_code=204)
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        return Response(content=str(e).encode(), status_code=500)
