# WhatsApp AI Agent

A conversational AI agent that reads and sends WhatsApp messages using natural language.
Built with **LangGraph** (agent brain) + **whatsapp-mcp** (WhatsApp bridge) + **Gemini**.

## Features
- Natural language to WhatsApp actions (send messages, search chats, read history)
- Confirms before sending any message (safety)
- Remembers conversation context (memory)
- 12 WhatsApp tools via Model Context Protocol (MCP)

## Tech Stack
- Python, LangGraph, LangChain
- langchain-mcp-adapters (MCP client)
- Google Gemini
- whatsapp-mcp (Go + Python bridge)

## Setup
1. Run the whatsapp-mcp bridge (see https://github.com/lharries/whatsapp-mcp) and scan the QR code to link your WhatsApp.
2. Create and activate a virtual environment:
   - `python -m venv venv`
   - `venv\Scripts\activate`  (Windows)
3. Install dependencies: `pip install -r requirements.txt`
4. Create a `.env` file in the project root with:
   - `MODEL=google_genai:gemini-flash-lite-latest`
   - `GOOGLE_API_KEY=your_key_here`
   - `WHATSAPP_MCP_PATH=path/to/whatsapp-mcp/whatsapp-mcp-server`
5. Run the agent: `python agent.py`

## How it works
You type a request in plain language. The LangGraph agent interprets it, asks for
confirmation, and then calls the appropriate WhatsApp MCP tool to carry it out.

## Note
This is a personal portfolio project for learning AI agents and tool-use.
