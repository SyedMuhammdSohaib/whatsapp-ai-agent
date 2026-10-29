import asyncio
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

MODEL = os.environ["MODEL"]
WHATSAPP_MCP_PATH = os.environ["WHATSAPP_MCP_PATH"]

SYSTEM_PROMPT = (
    "Tum ek helpful WhatsApp assistant ho. "
    "Hamesha Roman Urdu ya English me jawab do, Hindi ya Devanagari me nahi. "
    "Tumhare paas do tarah ke tools hain: WhatsApp (message bhejna/padhna) "
    "aur web search (tavily_search) - taaza ya real-time info ke liye. "
    "Jab user kisi nayi jaankari (mausam, rate, news, koi fact) ke baare me "
    "pooche, to pehle web search tool use karo, phir jawab do. "
    "Message bhejne se PEHLE user ko hamesha confirm karo. "
    "Jab user confirm kar de (haan / yes), to pichhle message ko bina dobara "
    "pooche send_message tool se bhej do. "
    "Tumhe baat-cheet yaad rehti hai, context use karo."
)

CONFIG = {"configurable": {"thread_id": "whatsapp-session"}}


async def build_agent():
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
    print(f"[ok] WhatsApp se {len(wa_tools)} tools load hue.")

    # Web search tool (Tavily)
    web = TavilySearch(max_results=1)
    tools = wa_tools + [web]
    print(f"[ok] Web search tool bhi add ho gaya. Total: {len(tools)} tools.")

    model = init_chat_model(MODEL, max_retries=6, timeout=120)
    memory = MemorySaver()
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT, checkpointer=memory)


async def main():
    agent = await build_agent()
    print("\nWhatsApp Agent ready (web search + memory). exit = band.\n")
    while True:
        user_input = input("tum> ").strip()
        if user_input.lower() in {"exit", "quit", "q"}:
            break
        if not user_input:
            continue
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=CONFIG,
            )
            print(f"agent> {result['messages'][-1].content}\n")
        except Exception as e:
            print(f"[network/error] {type(e).__name__}: {e}")
            print("[info] Phir se likho - connection slow tha shayad.\n")


if __name__ == "__main__":
    asyncio.run(main())
