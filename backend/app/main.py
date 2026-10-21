import secrets
import time
from pathlib import Path
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import rag
from .config import settings
from .db import close_pool, get_conn, init_pool
from .guardrails import check_input, fence_context, scrub_output
from .llm import generate
from .persona import system_prompt

Mode = Literal["presentation", "companion"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_pool()
    yield
    close_pool()


app = FastAPI(title="Digital Me", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # tighten for prod
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- auth / limits
def require_owner(x_api_key: str | None = Header(default=None)) -> None:
    """Placeholder auth: one shared secret. Replace with JWT/OAuth in step 2."""
    expected = settings.companion_api_key
    if not expected or not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    """Naive in-memory sliding window per client IP. Use Redis once you run >1 instance."""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.public_rate_limit_per_min:
        raise HTTPException(status_code=429, detail="Too many requests, slow down.")
    window.append(now)


# ---------------------------------------------------------------- schemas
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    mode: Mode
    message: str
    history: list[Turn] = []


class ChatResponse(BaseModel):
    mode: Mode
    answer: str
    sources: list[str] = []


class IngestRequest(BaseModel):
    scope: Literal["public", "private"]
    source: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)


# ---------------------------------------------------------------- routes
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/companion/check", dependencies=[Depends(require_owner)])
def companion_check():
    """Lets the chat page verify the access key before showing Companion mode."""
    return {"ok": True}


@app.post("/ingest", dependencies=[Depends(require_owner)])
def ingest(body: IngestRequest):
    count = rag.ingest(body.scope, body.source, body.text)
    return {"scope": body.scope, "source": body.source, "chunks": count}


@app.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    x_api_key: str | None = Header(default=None),
):
    # Mode decides everything: auth, retrieval scope, prompt, logging.
    if body.mode == "companion":
        require_owner(x_api_key)
        scope = "private"
    else:
        rate_limit(request)
        scope = "public"

    check = check_input(body.message, body.mode)
    if not check.ok:
        if check.flagged:
            _log(body.mode, body.message, check.reason, flagged=True)
        return ChatResponse(mode=body.mode, answer=check.reason)

    chunks = rag.retrieve(scope, body.message)

    # Only the user/assistant turns the client sent, trimmed. The retrieved context goes
    # into the final user turn, fenced as data.
    history = [t.model_dump() for t in body.history[-settings.max_history_turns :]]
    user_turn = (
        f"{fence_context(chunks)}\n\n"
        f"<visitor_message>\n{body.message.strip()}\n</visitor_message>"
        if body.mode == "presentation"
        else f"{fence_context(chunks)}\n\n<my_message>\n{body.message.strip()}\n</my_message>"
    )
    messages = history + [{"role": "user", "content": user_turn}]

    try:
        answer = generate(system_prompt(body.mode), messages)
    except RuntimeError as e:  # misconfiguration, e.g. missing key
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # provider error: bad key, wrong model name, rate limit
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")

    answer = scrub_output(answer, body.mode)

    # Privacy: companion conversations are never written to the database.
    if body.mode == "presentation":
        _log(body.mode, body.message, answer, flagged=check.flagged)

    sources = sorted({c["source"] for c in chunks if c["score"] > 0.3})
    return ChatResponse(mode=body.mode, answer=answer, sources=sources)


def _log(mode: str, question: str, answer: str, flagged: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_logs (mode, question, answer, flagged) VALUES (%s, %s, %s, %s)",
            (mode, question, answer, flagged),
        )


# Serve the chat page at "/". Mounted last so it never shadows the API routes or /docs.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
