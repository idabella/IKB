"""
AI Chat router — Gemini-powered assistant with machine context injection.

Requires GEMINI_API_KEY in backend/.env (copy from .env.example).
If the key is absent the endpoint returns a stub response so the rest of
the app remains functional.
"""

import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

try:
    from database import get_session
    from models import Machine, Alert, Document
except ImportError:
    from backend.database import get_session
    from backend.models import Machine, Alert, Document

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

router = APIRouter(prefix="/api/chat", tags=["chat"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Industrial Knowledge Brain (IKB) AI assistant.
You help maintenance engineers diagnose machine issues, interpret sensor data,
recommend corrective actions, and search through the knowledge base.

Guidelines:
- Be concise and technical. Prioritise actionable recommendations.
- Always cite the relevant machine name and sensor values when discussing issues.
- If you recommend a procedure, mention the relevant document if known.
- If unsure, say so clearly and suggest who to escalate to.
- Keep responses under 250 words unless asked for more detail.
"""

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatTurn(BaseModel):
    role: str       # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    machine_id: Optional[str] = None
    history: List[ChatTurn] = []


class ChatResponse(BaseModel):
    reply: str
    sources: List[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_machine_context(machine_id: str, session: Session) -> str:
    """Return a brief text summary of a machine's current state."""
    m = session.get(Machine, machine_id)
    if not m:
        return ""
    active_alerts = session.exec(
        select(Alert).where(Alert.machine == m.name, Alert.status == "active")
    ).all()
    alert_summary = (
        "; ".join(f"{a.type} ({a.severity})" for a in active_alerts)
        if active_alerts else "none"
    )
    return (
        f"\n--- MACHINE CONTEXT ---\n"
        f"Name: {m.name}\n"
        f"Type: {m.type}\n"
        f"Status: {m.status}\n"
        f"Temperature: {m.temp}°C\n"
        f"Vibration: {m.vibration} mm/s\n"
        f"RPM: {m.rpm}\n"
        f"Pressure: {m.pressure} bar\n"
        f"Efficiency: {m.efficiency}%\n"
        f"Location: {m.location} — {m.department}\n"
        f"Active alerts: {alert_summary}\n"
        f"--- END CONTEXT ---\n"
    )


def _find_relevant_docs(query: str, session: Session) -> List[str]:
    """Return titles of documents that mention keywords from the query."""
    docs = session.exec(select(Document)).all()
    ql = query.lower()
    hits = [
        d.title for d in docs
        if any(word in d.title.lower() or word in d.excerpt.lower()
               for word in ql.split() if len(word) > 3)
    ]
    return hits[:3]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, session: Session = Depends(get_session)):
    machine_ctx = (
        _build_machine_context(body.machine_id, session)
        if body.machine_id else ""
    )
    relevant_docs = _find_relevant_docs(body.message, session)

    # ------- No API key → polite stub -------
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        stub = (
            "⚠️  AI chat is not configured yet. "
            "Add your GEMINI_API_KEY to backend/.env to enable it.\n\n"
            "Based on current telemetry and the knowledge base I can still "
            "provide context-aware recommendations once the key is set."
        )
        return ChatResponse(reply=stub, sources=relevant_docs)

    # ------- Gemini call -------
    try:
        import time
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=GEMINI_API_KEY)

        # Model chain: try models in order until one succeeds.
        # gemini-2.0-flash-lite is the lightest model and least likely to hit quota.
        MODEL_CHAIN = [
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.5-flash",
        ]

        # Build the conversation history for the model
        gemini_history = []
        for turn in body.history:
            gemini_history.append({
                "role": "user" if turn.role == "user" else "model",
                "parts": [turn.content],
            })

        # Prepend machine context to the current user message
        user_message = machine_ctx + body.message
        gemini_history.append({"role": "user", "parts": [user_message]})

        reply_text = None
        last_error = None

        for model_name in MODEL_CHAIN:
            for attempt in range(3):  # up to 3 retries per model
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=SYSTEM_PROMPT,
                    )
                    response = model.generate_content(gemini_history)
                    reply_text = response.text.strip()
                    break  # success — exit retry loop
                except Exception as exc:
                    last_error = exc
                    err_str = str(exc)
                    if "429" in err_str or "quota" in err_str.lower():
                        if attempt < 2:
                            time.sleep(2 ** attempt)  # 1s, 2s backoff
                            continue
                        else:
                            break  # quota exhausted for this model, try next
                    else:
                        raise  # non-quota error — propagate immediately
            if reply_text is not None:
                break  # got a response, no need to try more models

        if reply_text is None:
            reply_text = (
                "⚠️ All available AI models have reached their free-tier quota limit. "
                "Options to restore service:\n"
                "1. **Wait** — quota resets daily (usually at midnight UTC).\n"
                "2. **Upgrade** — enable billing on your Google AI Studio project at https://ai.dev/rate-limit.\n"
                "3. **Use a different API key** — set a new GEMINI_API_KEY in backend/.env.\n\n"
                f"Last error: {last_error}"
            )

    except Exception as exc:
        reply_text = (
            f"I encountered an unexpected error: {exc}\n"
            "Please check your GEMINI_API_KEY and network connectivity."
        )

    return ChatResponse(reply=reply_text, sources=relevant_docs)
