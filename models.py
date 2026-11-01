"""
Model setup: pehle .env wala MODEL chalta hai, limit khatam ho to agla model khud chal jata hai.
"""

import os

from langchain.agents.middleware import ModelFallbackMiddleware
from langchain.chat_models import init_chat_model

# Isi tarteeb se try honge. Sab ek hi GROQ_API_KEY par chalte hain.
FALLBACK_MODELS = ["groq:openai/gpt-oss-120b", "groq:qwen/qwen3.8-27b"]
MAX_RETRIES = 2  # zyada retry par limit ke error me agle model tak jane me der lagti hai
MAX_OUTPUT_TOKENS = 2000  # had na ho to qwen "Request too large" (429) deta hai


def make_model(name):
    return init_chat_model(name, max_retries=MAX_RETRIES, timeout=120, max_tokens=MAX_OUTPUT_TOKENS)


def _fallbacks():
    return [make_model(name) for name in FALLBACK_MODELS if name != os.environ["MODEL"]]


def fallback_middleware():
    # Agent ke liye
    return ModelFallbackMiddleware(*_fallbacks())


def model_with_fallbacks():
    # Agent ke bahar seedhi model call ke liye
    return make_model(os.environ["MODEL"]).with_fallbacks(_fallbacks())
