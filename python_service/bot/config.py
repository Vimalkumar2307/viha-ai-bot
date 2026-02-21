"""
LLM configuration and setup
"""

import os
from langchain_groq import ChatGroq

def get_llm():
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

llm = get_llm()