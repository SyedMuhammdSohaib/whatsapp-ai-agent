"""
YouTube tools: video/gaana dhoondho, player control karo, video ka content samjhao.
Player browser me chalta hai, is liye play/control tools sirf ek command (artifact)
dete hain jo /chat ke zariye frontend tak jati hai.
"""

import asyncio
import os
from typing import Literal

import yt_dlp
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from youtube_transcript_api import YouTubeTranscriptApi

SEARCH_RESULTS = 5  # kuch videos embed nahi hoti, player phir agli try karta hai
MAX_TRANSCRIPT_CHARS = 12000  # Groq token limit ke andar rehne ke liye
NEARBY_SECONDS = 60  # "abhi kya chal raha hai" ke liye current time ke aas paas ka text
TRANSCRIPT_LANGUAGES = ["ur", "hi", "en"]
DEFAULT_SKIP_SECONDS = 10  # "aage karo" bina waqt bataye

_model = None


def _search(query):
    options = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch{SEARCH_RESULTS}:{query}", download=False)
    return [
        {"id": e["id"], "title": e.get("title") or e["id"]}
        for e in info.get("entries", [])
        if e.get("id")
    ]


def _details(video_id):
    options = {"quiet": True, "no_warnings": True, "skip_download": True, "ignore_no_formats_error": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)


def _transcript(video_id):
    # [(seconds, text), ...] ya None agar is video ki transcript nahi hai
    try:
        available = YouTubeTranscriptApi().list(video_id)
        try:
            chosen = available.find_transcript(TRANSCRIPT_LANGUAGES)
        except Exception:
            chosen = next(iter(available))
        return [(s.start, s.text) for s in chosen.fetch()]
    except Exception:
        return None


def _as_lines(snippets):
    return "\n".join(f"[{int(start)}s] {text}" for start, text in snippets)


def _fit_transcript(snippets, video_time):
    # Lambi video ka sirf shuru na bheje, poori video me se barabar faslay se text le
    text = _as_lines(snippets)
    if len(text) <= MAX_TRANSCRIPT_CHARS:
        return text
    step = len(text) / MAX_TRANSCRIPT_CHARS
    sampled = [s for i, s in enumerate(snippets) if int(i / step) != int((i - 1) / step)]
    nearby = [s for s in snippets if abs(s[0] - video_time) <= NEARBY_SECONDS]
    return (
        f"(Video lambi hai, poori video me se hisse liye gaye hain)\n{_as_lines(sampled)}"
        f"\n\nAbhi chalne wali jagah ke aas paas:\n{_as_lines(nearby)}"
    )


@tool(response_format="content_and_artifact")
def play_youtube(query: str):
    """YouTube par koi bhi video ya gaana dhoond kar app ke player me chalao."""
    try:
        videos = _search(query)
    except Exception as e:
        return f"YouTube search nahi ho saki: {e}", None
    if not videos:
        return f"'{query}' ke liye YouTube par kuch nahi mila.", None
    return f"Chala di: {videos[0]['title']}", {"youtube": {"action": "play", "videos": videos}}


@tool(response_format="content_and_artifact")
def control_youtube(
    action: Literal["pause", "resume", "forward", "backward", "seek_to", "stop"],
    minutes: int = 0,
    seconds: int = 0,
):
    """Chalti hui video ko control karo. forward/backward: itna waqt aage/peeche.
    seek_to: video ke is waqt par jao. "5 minute" ho to minutes=5, "30 second" ho to
    seconds=30. "Rok do" ka matlab pause hai. stop sirf tab jab user player band karna
    chahe. pause, resume, stop me waqt ki zaroorat nahi."""
    total = minutes * 60 + seconds
    if action in ("forward", "backward") and not total:
        total = DEFAULT_SKIP_SECONDS
    return f"Ho gaya: {action} ({total} second)", {"youtube": {"action": action, "seconds": total}}


@tool
async def explain_youtube_video(question: str, config: RunnableConfig) -> str:
    """Chalti hui video ke andar kya hai batao ya use samjhao. Summary, kisi topic ki
    wazahat, ya video se juda koi bhi sawal ho to ye tool use karo."""
    global _model
    settings = config.get("configurable", {})
    video_id = settings.get("video_id")
    video_time = settings.get("video_time", 0)
    if not video_id:
        return "Abhi koi video nahi chal rahi. User se poocho kaun si video chalani hai."

    snippets, details = await asyncio.gather(
        asyncio.to_thread(_transcript, video_id),
        asyncio.to_thread(_details, video_id),
    )
    title = details.get("title", "")
    if snippets:
        source = f"Transcript ([Ns] = video ka second):\n{_fit_transcript(snippets, video_time)}"
    else:
        source = (
            "Is video ki transcript nahi hai, sirf ye maloomat hai, aur user ko ye baat batao:\n"
            f"{(details.get('description') or '')[:MAX_TRANSCRIPT_CHARS]}"
        )

    if _model is None:
        _model = init_chat_model(os.environ["MODEL"], max_retries=6, timeout=120)
    result = await _model.ainvoke(
        f"Video: {title}\nUser abhi video ke {int(video_time)} second par hai.\n\n{source}\n\n"
        f"Sawal: {question}\n\n"
        "Sirf upar di gayi maloomat se jawab do, apni taraf se kuch na banao. "
        "Gaana ho to bol na dohrao, uska matlab aur mazmoon apne alfaaz me samjhao. "
        "Jawab user ki zaban me do, seedha aur wazeh."
    )
    return result.text() if callable(getattr(result, "text", None)) else str(result.content)


YOUTUBE_TOOLS = [play_youtube, control_youtube, explain_youtube_video]
