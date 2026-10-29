import asyncio
import json
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage
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
    "Jab user kisi ko NAAM se message bhejne ko kahe, to number mat maango. "
    "Pehle search_contacts tool se us naam ko dhoondo; na mile to list_chats "
    "tool me us naam se chat dhoondo. Ek hi contact mile to uska JID (ya "
    "number) send_message ke recipient me use karo. Kai contacts milen to "
    "unki list (naam + number) dikha kar poocho kaunsa. Number sirf tab maango "
    "jab kisi tool se bhi contact na mile. "
    "Message bhejne se PEHLE user ko hamesha confirm karo, aur confirm karte "
    "waqt contact ka naam aur number dono dikhao. "
    "Jab user confirm kar de (haan / yes), to pichhle message ko bina dobara "
    "pooche send_message tool se bhej do. "
    "Tumhe baat-cheet yaad rehti hai, context use karo."
)

CONFIG = {"configurable": {"thread_id": "whatsapp-session"}}


@wrap_tool_call
async def tool_result_as_text(request, handler):
    # Groq tool messages me sirf non-empty string chalti hai. WhatsApp MCP tools
    # kabhi khali content (sirf structured data) ya content blocks ki list dete
    # hain, is liye unhe ek text string me badal dete hain.
    result = await handler(request)
    if not isinstance(result, ToolMessage) or (isinstance(result.content, str) and result.content):
        return result
    if isinstance(result.content, list):
        parts = [b if isinstance(b, str) else b.get("text", "") for b in result.content]
        text = "\n".join(p for p in parts if p)
    else:
        text = result.content
    if not text and isinstance(result.artifact, dict) and result.artifact.get("structured_content"):
        text = json.dumps(result.artifact["structured_content"], ensure_ascii=False)
    result.content = text or "Done (tool ne koi output nahi diya)."
    return result


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
    return create_agent(
        model,
        tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[tool_result_as_text],
        checkpointer=memory,
    )


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
