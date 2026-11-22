"""Shopping agent built with LangChain + gpt-oss-120b on GroqCloud."""

import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_groq import ChatGroq

from tools import list_orders, place_order, search_products

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are a friendly shopping assistant for an online grocery store.
- Use `search_products` to find items. Always pass filters (max_price, min_price, min_rating, organic_only) \
when the user states them.
- Show results concisely with product ID, name, price, rating (and review count) and organic status.
- Only place an order with `place_order` when the user clearly asks to buy/order a specific item. \
If the request is ambiguous (several matches), ask which product first. Never invent products or IDs.
- When asked about orders ("show my orders", "what did I order"), ALWAYS call `list_orders` and \
show every order it returns; never rely on chat history for this.
- After ordering, confirm the order ID, product and price.
"""


def build_agent():
    llm = ChatGroq(model=MODEL, temperature=0)
    return create_agent(llm, tools=[search_products, place_order, list_orders], system_prompt=SYSTEM_PROMPT)


def to_lc_messages(history: list[dict]) -> list[tuple[str, str]]:
    return [(m["role"], m["content"]) for m in history]


def ask(agent, history: list[dict]) -> str:
    """history: [{'role': 'user'|'assistant', 'content': str}, ...] ending with a user message."""
    result = agent.invoke({"messages": to_lc_messages(history)})
    return result["messages"][-1].content
