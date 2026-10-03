from langchain_groq import ChatGroq
from pydantic import BaseModel

llm = ChatGroq(model="openai/gpt-oss-120b")

