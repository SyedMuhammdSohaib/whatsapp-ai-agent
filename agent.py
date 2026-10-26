import asyncio
import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

load_dotenv()

MODEL = os.environ["MODEL"]
WHATSAPP_MCP_PATH = os.environ["WHATSAPP_MCP_PATH"]

SYSTEM_PROMPT = (
    "Tum ek helpful WhatsApp assistant ho. "
    "Message bhejne se PEHLE user ko hamesha confirm karo. "
    "Jab user confirm kar de (haan / yes), to pichhle message ko "
    "bina dobara pooche send_message tool se bhej do. "
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
    tools = await client.get_tools()
    print(f"[ok] WhatsApp se {len(tools)} tools load hue:")
    for t in tools:
        print(f"     - {t.name}")
    model = init_chat_model(MODEL, max_retries=6, timeout=120)
    memory = MemorySaver()
    return create_react_agent(model, tools, prompt=SYSTEM_PROMPT, checkpointer=memory)


async def main():
    agent = await build_agent()
    print("\nWhatsApp Agent ready (yaadasht ke saath). exit = band.\n")
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
            print("[info] Phir se likho - net slow tha shayad.\n")


if __name__ == "__main__":
    asyncio.run(main())
