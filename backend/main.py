import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from rag.retiever import run_rag

app = FastAPI(title="SAP Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    module: Optional[str] = None
    sources: list[str] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    answer = run_rag(req.message, req.history)

    return ChatResponse(
        reply=answer["text"],
        module=answer.get("module"),
        sources=answer.get("sources", []),
    )