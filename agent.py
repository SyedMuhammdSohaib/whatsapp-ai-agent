import asyncio
import json
import os

import voice
from contacts import find_contact
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call, wrap_tool_call
from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from memories import MEMORY_TOOLS, add_memories, guard_memory, make_checkpointer
from models import fallback_middleware, make_model
from pydantic import BaseModel, Field
from send_guard import answer_pending, hold_for_approval, pending_prompt
from whatsapp_summary import WHATSAPP_SUMMARY_TOOLS

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
    "Pehle find_contact tool se us naam ko dhoondo (ye phone me save kiye "
    "naam bhi dekhta hai). Ek hi contact mile to uska recipient "
    "send_message me use karo. Kai contacts milen to unki list (naam + "
    "number) dikha kar poocho kaunsa. Number sirf tab maango jab find_contact "
    "se bhi contact na mile. "
    "User kabhi bol kar (voice) likhwata hai, to text Urdu script me ya "
    "galat spelling ke saath aa sakta hai; naam ko Roman/English me badal kar "
    "find_contact karo, aur jawab hamesha Roman Urdu me do. "
    "Message bhejne ke liye seedha send_message chalao, khud confirm mat poocho. System "
    "bhejne se pehle user se khud confirm karwata hai aur user ka jawab bhi khud sambhalta hai. "
    "User 'yaad rakho' kahe to remember_fact, yaad rakhi baatein dekhne ko list_memories, aur hatane ko forget_memory use karo. "
    "Tumhe baat-cheet yaad rehti hai, context use karo."
)

CONFIG = {"configurable": {"thread_id": "whatsapp-session"}}

# Groq ki rozana token limit bachane ke liye model ko sirf haal ki baat-cheet jati hai
HISTORY_TURNS = 6
OLD_TOOL_RESULT_CHARS = 500


def recent_messages(messages):
    # User ke sawal se shuru karo, taake tool result apni tool call ke baghair na jaye
    human_indexes = [i for i, m in enumerate(messages) if m.type == "human"]
    if not human_indexes:
        return messages
    start = human_indexes[-HISTORY_TURNS] if len(human_indexes) > HISTORY_TURNS else 0
    current_turn = human_indexes[-1]
    recent = []
    for i, m in enumerate(messages[start:], start):
        too_long = isinstance(m.content, str) and len(m.content) > OLD_TOOL_RESULT_CHARS
        if m.type == "tool" and i < current_turn and too_long:
            m = m.model_copy(update={"content": m.content[:OLD_TOOL_RESULT_CHARS] + " ...(chhota kiya gaya)"})
        recent.append(m)
    return recent


@wrap_model_call
async def send_recent_history(request, handler):
    return await handler(request.override(messages=recent_messages(request.messages)))


# Model ko sirf query do — warna woh ghalat topic (jaise "weather") bhej deta hai aur Groq 400 deta hai
class WebSearchInput(BaseModel):
    query: str = Field(description="Web par search karne ke liye query")


@wrap_tool_call
async def tool_result_as_text(request, handler):
    # Groq tool messages me sirf non-empty string chalti hai. WhatsApp MCP tools
    # kabhi khali content (sirf structured data) ya content blocks ki list dete
    # hain, is liye unhe ek text string me badal dete hain.
    print(f"[tool] {request.tool_call['name']}({request.tool_call['args']})")
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

    # Web search (Tavily) + naam se contact dhoondhne wala tool
    web = TavilySearch(max_results=1, args_schema=WebSearchInput)
    tools = wa_tools + [web, find_contact] + WHATSAPP_SUMMARY_TOOLS + MEMORY_TOOLS
    print(f"[ok] Web search aur find_contact tools bhi add ho gaye. Total: {len(tools)} tools.")

    model = make_model(MODEL)
    memory = await make_checkpointer()
    return create_agent(
        model,
        tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[add_memories, send_recent_history, fallback_middleware(), tool_result_as_text, guard_memory, hold_for_approval],
        checkpointer=memory,
    )


async def main():
    agent = await build_agent()
    print("\nWhatsApp Agent ready (web search + memory + voice).")
    print("Likh kar poocho, ya sirf Enter dabao aur bol kar poocho. exit = band.\n")
    while True:
        user_input = input("tum> ").strip()
        if user_input.lower() in {"exit", "quit", "q"}:
            break
        if not user_input:
            try:
                user_input = voice.listen()
            except Exception as e:
                print(f"[voice/error] {type(e).__name__}: {e}\n")
                continue
            if not user_input:
                print("[mic] Kuch sunai nahi diya.\n")
                continue
            print(f"[suna] {user_input}")
        try:
            reply, note = await answer_pending(agent, CONFIG, user_input)
            if reply:
                print(f"agent> {reply}\n")
                continue
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=CONFIG,
            )
            reply = pending_prompt(CONFIG["configurable"]["thread_id"]) or result["messages"][-1].content
            print(f"agent> {note}{reply}\n")
        except Exception as e:
            print(f"[network/error] {type(e).__name__}: {e}")
            print("[info] Phir se likho - connection slow tha shayad.\n")
    await agent.checkpointer.conn.close()


if __name__ == "__main__":
    asyncio.run(main())
