# WhatsApp AI Agent

A conversational AI agent that reads and sends WhatsApp messages using natural language.
Built with **LangGraph** (agent brain) + **whatsapp-mcp** (WhatsApp bridge) + **Groq** or **Gemini** (LLM) + **Tavily** (web search).

## Features
- Natural language to WhatsApp actions (send messages, search chats, read history)
- Sending is held in code until you say yes, and shows exactly who and what will be sent (safety)
- Remembers conversations across restarts, and facts you explicitly ask it to remember
- 12 WhatsApp tools via Model Context Protocol (MCP)
- Web search (Tavily) for real-time info like weather, rates and news
- Voice input: press Enter on an empty prompt, speak, press Enter again (Groq Whisper speech-to-text)
- Send by contact name: looks up names saved on your phone (from the bridge database), no phone number needed
- WhatsApp summaries: see who messaged you and get a summary of one chat, a group or the whole day (read-only, by contact name)
- Scheduled messages in the web app: "send this tomorrow at 9", with list and cancel; saved across restarts, sent while the backend and bridge are running
- Reminders in the web app: "remind me tomorrow at 9", shown in the chat and spoken; if the app was closed, shown when it opens
- Daily briefing in the web app: today's reminders and scheduled messages, weather and a WhatsApp summary, on the day's first open or on request. Set `BRIEFING_CITY` in `.env` to include the weather
- YouTube in the web app: play any video or song, pause, resume, skip forward or back, and ask what a video contains (uses its transcript)

## Tech Stack
- Python, LangGraph, LangChain
- langchain-mcp-adapters (MCP client)
- Groq or Google Gemini
- Tavily web search
- whatsapp-mcp (Go + Python bridge)

## Setup
1. Run the whatsapp-mcp bridge (see https://github.com/lharries/whatsapp-mcp) and scan the QR code to link your WhatsApp.
2. Create and activate a virtual environment:
   - `python -m venv venv`
   - `venv\Scripts\activate`  (Windows)
3. Install dependencies: `pip install -r requirements.txt`
4. Create a `.env` file in the project root with:
   - `MODEL=groq:llama-3.3-70b-versatile` and `GROQ_API_KEY=your_key_here`
     (or `MODEL=google_genai:gemini-flash-lite-latest` and `GOOGLE_API_KEY=your_key_here`)
   - `TAVILY_API_KEY=your_key_here` (for web search, get one at https://tavily.com)
   - `WHATSAPP_MCP_PATH=path/to/whatsapp-mcp/whatsapp-mcp-server`
5. Run the agent: `python agent.py`
   - Type a request, or press Enter on an empty `tum>` prompt to speak it (needs a microphone and `GROQ_API_KEY`).

## How it works
You type a request in plain language. The LangGraph agent interprets it, asks for
confirmation, and then calls the appropriate WhatsApp MCP tool to carry it out.
For questions that need fresh information, it searches the web first.

Conversations are saved in `chat_history.db` and facts you ask it to remember in `memories.db`, so both survive restarts. Both files stay on your computer and out of git. Stop the app and delete them to erase its memory.

To save tokens, only the last 6 turns are sent to the model. If a model fails or hits its rate limit, the agent switches to the next one in `FALLBACK_MODELS` (`models.py`).

## Note
This is a personal portfolio project for learning AI agents and tool-use.
