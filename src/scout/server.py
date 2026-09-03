"""An OpenAI-compatible HTTP face for the agent.

OpenWebUI, the personal page and anything else that already speaks to OpenAI can
speak to this without knowing what LangGraph is. The shim is deliberately thin:
it authenticates the caller, decides which of the two agents to run, translates
the message list in and the token stream out, and does nothing else. Every rule
about what the agent may do lives in the agent.

An OpenAI client resends the whole conversation on every turn, but only the
prose: the tool calls the agent made, their results and its todo list are not
part of the protocol and never come back. Served statelessly, the agent saw its
own previous answer and none of the work behind it, and reran the same research
to reproduce the same table. So the shim keeps a checkpoint thread per client
conversation when the client identifies one (`X-Scout-Chat-Id`), feeds only the
new turn into it, and lets the checkpointer carry the rest. Without the header
it behaves as before. Long-term memory — job dossiers and profiles in the store
— is separate from either and keyed by the caller's identity.

Two identities exist. The owner is whoever presents the owner token and gets the
full agent. Everyone else is a guest: a read-only agent, no LinkedIn account, no
access to the owner's Candidate Profile, and a request budget. The guest token
is not a secret in any real sense — it ships inside a public web page — so it is
treated as a gate against casual traffic, and the protections that matter are
the capability restrictions and the budget behind it.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.store.base import BaseStore
from pydantic import BaseModel

from .config import get_config, get_settings
from .identity import Identity, run_context
from .memory import open_memory

logger = logging.getLogger(__name__)

OWNER_MODEL = "agentic-sdlc-scout"
GUEST_MODEL = "agentic-sdlc-scout-guest"

# The client's conversation id, if it sends one. OpenWebUI is configured in
# docker-compose.yml to put its chat id here on every request.
CHAT_ID_HEADER = "X-Scout-Chat-Id"


class ChatMessage(BaseModel):
    """One message in the conversation, as an OpenAI client sends it."""

    role: Literal["system", "user", "assistant", "tool", "developer"]
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    """The subset of the OpenAI request the shim honours.

    Sampling parameters are accepted and ignored rather than rejected: clients
    send them unprompted, and refusing the request over a field the agent has no
    use for would fail a conversation for no reason.
    """

    model: str = OWNER_MODEL
    messages: list[ChatMessage]
    stream: bool = False
    user: str | None = None

    model_config = {"extra": "ignore"}


class RateLimiter:
    """A sliding window of request timestamps per identity.

    In-process on purpose. It resets on restart and does not span replicas, and
    for a single container in front of one person's OpenAI balance that is
    enough. The point is not perfect accounting; it is that a public page cannot
    quietly drain the owner's credit overnight.
    """

    def __init__(self, per_hour: int, per_day: int) -> None:
        self.per_hour = per_hour
        self.per_day = per_day
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> str | None:
        """Record a request, or explain why it is refused."""
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > 86400:
            hits.popleft()

        if len(hits) >= self.per_day:
            return f"Daily limit reached ({self.per_day} requests). Try again tomorrow."

        recent = sum(1 for t in hits if now - t <= 3600)
        if recent >= self.per_hour:
            return f"Hourly limit reached ({self.per_hour} requests). Try again later."

        hits.append(now)
        return None


class AgentRegistry:
    """The two built agents and the store they share.

    Both are assembled once at startup. Building an agent opens the LinkedIn MCP
    process and reads the skills off disk, which is far too much work to repeat
    on every HTTP request.
    """

    def __init__(self) -> None:
        self.store: BaseStore | None = None
        self.owner: Any = None
        self.guest: Any = None

    def for_identity(self, identity: Identity) -> Any:
        """The agent this caller is entitled to."""
        return self.guest if identity.is_guest else self.owner


registry = AgentRegistry()
limiter: RateLimiter | None = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open memory and build both agents once, for the life of the process."""
    global limiter
    from .agent import build_agent

    settings = get_settings()
    budgets = get_config().budgets
    limiter = RateLimiter(
        per_hour=getattr(budgets, "guest_requests_per_hour", 20),
        per_day=getattr(budgets, "guest_requests_per_day", 100),
    )

    async with open_memory() as (store, saver):
        registry.store = store
        registry.owner = await build_agent(store=store, checkpointer=saver)
        registry.guest = await build_agent(store=store, checkpointer=saver, guest=True)
        logger.info(
            "Serving as %s; guest access %s",
            OWNER_MODEL,
            "enabled" if settings.scout_guest_enabled else "disabled",
        )
        yield

    registry.store = registry.owner = registry.guest = None


app = FastAPI(title="Agentic SDLC Scout", lifespan=lifespan)


def authenticate(request: Request) -> Identity:
    """Resolve the bearer token into an identity, or refuse.

    An unset owner token is treated as a misconfiguration rather than as an open
    door. Defaulting to unauthenticated access would be the kind of decision
    that is invisible until the day the port is public.
    """
    settings = get_settings()
    token = _bearer(request)

    if not settings.scout_owner_token:
        raise HTTPException(
            status_code=503,
            detail="SCOUT_OWNER_TOKEN is not configured, so no caller can be authenticated.",
        )

    if token and _constant_time_equals(token, settings.scout_owner_token):
        return Identity(user_id=settings.scout_user_id, is_guest=False)

    if settings.scout_guest_enabled:
        guest_token = settings.scout_guest_token
        if not guest_token or (token and _constant_time_equals(token, guest_token)):
            return Identity(user_id=_guest_id(request), is_guest=True)

    raise HTTPException(status_code=401, detail="Invalid or missing bearer token.")


@app.get("/health")
async def health() -> dict[str, Any]:
    """Whether the process is up and what it has managed to attach."""
    return {
        "status": "ok" if registry.owner is not None else "starting",
        "guest_access": get_settings().scout_guest_enabled,
        "memory": "postgres" if get_settings().has_postgres else "in-memory",
    }


@app.get("/v1/models")
async def list_models(identity: Identity = Depends(authenticate)) -> dict[str, Any]:
    """The model list an OpenAI client fetches to populate its picker.

    A guest is shown only the guest model. Advertising the owner's model to a
    visitor invites them to select it and be refused, which reads as a fault.
    """
    names = [GUEST_MODEL] if identity.is_guest else [OWNER_MODEL, GUEST_MODEL]
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "created": created, "owned_by": "agentic-sdlc-scout"}
            for name in names
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    identity: Identity = Depends(authenticate),
) -> Any:
    """Run one turn of the conversation."""
    if registry.owner is None:
        raise HTTPException(status_code=503, detail="The agent is still starting.")

    if limiter is not None:
        refusal = limiter.check(identity.user_id)
        if refusal:
            raise HTTPException(status_code=429, detail=refusal)

    # A guest asking for the owner model gets the guest agent regardless. The
    # model name arrives from the client and is not a credential.
    agent = registry.for_identity(identity)
    messages = _to_langchain(body.messages)
    if not messages:
        raise HTTPException(status_code=400, detail="No messages to answer.")

    chat_id = request.headers.get(CHAT_ID_HEADER)
    config = {"configurable": {**run_context(identity), "thread_id": thread_id(identity, chat_id)}}
    if chat_id and await _thread_has_history(agent, config):
        messages = _latest_turn(messages)
    model_name = GUEST_MODEL if identity.is_guest else OWNER_MODEL

    if body.stream:
        return StreamingResponse(
            _stream(agent, messages, config, model_name),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = await agent.ainvoke({"messages": messages}, config=config)
    return _completion(model_name, _final_text(result))


async def _stream(
    agent: Any, messages: list[dict], config: dict, model_name: str
) -> AsyncIterator[str]:
    """Translate the agent's token stream into OpenAI server-sent events."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    def event(delta: dict, finish: str | None = None) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield event({"role": "assistant", "content": ""})
    try:
        async for chunk, meta in agent.astream(
            {"messages": messages}, config=config, stream_mode="messages"
        ):
            if not _is_user_facing(chunk, meta):
                continue
            text = _text_of(chunk)
            if text:
                yield event({"content": text})
    except Exception as exc:
        logger.exception("The run failed")
        yield event({"content": f"\n\nThe run failed: {exc}"})

    yield event({}, finish="stop")
    yield "data: [DONE]\n\n"


def _is_user_facing(chunk: Any, meta: dict) -> bool:
    """Whether a streamed chunk belongs in the user's chat window.

    Two things have to be excluded. Subagents run inside the `task` tool under a
    nested checkpoint namespace, and their working notes are meant to stay there
    — the whole point of the subagent design is that only the conclusion travels
    upstream. Anything that is not the orchestrator's own model node is likewise
    machinery rather than an answer.

    The summarisation model is handled elsewhere, by a tag that keeps it out of
    the stream entirely.
    """
    if chunk.__class__.__name__ != "AIMessageChunk":
        return False
    if meta.get("langgraph_node") != "model":
        return False
    # "|" is LangGraph's namespace separator; its presence means nesting.
    return "|" not in str(meta.get("checkpoint_ns") or "")


def _text_of(chunk: Any) -> str:
    """The plain text of a chunk, whether its content is a string or blocks."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def _final_text(result: dict) -> str:
    """The last assistant message of a non-streamed run."""
    for message in reversed(result.get("messages") or []):
        if message.__class__.__name__.startswith("AI"):
            text = _text_of(message)
            if text:
                return text
    return ""


def _completion(model_name: str, text: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
    }


def _to_langchain(messages: list[ChatMessage]) -> list[dict]:
    """Flatten the client's messages into the shape the graph expects."""
    out: list[dict] = []
    for message in messages:
        content = message.content
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        if not content:
            continue
        # `tool` and `developer` have no counterpart in a fresh run: there is no
        # tool call for a result to answer, and the developer role is the shim's
        # own system prompt, which the agent supplies itself.
        role = {"developer": "system", "tool": "user"}.get(message.role, message.role)
        out.append({"role": role, "content": content})
    return out


def thread_id(identity: Identity, chat_id: str | None) -> str:
    """The checkpoint thread for this request.

    Namespaced by identity, so two callers who happen to present the same chat id
    — OpenWebUI ids are uuids, but the header is client-supplied and nothing
    stops a guest from sending the owner's — cannot read or extend each other's
    conversation. Without a chat id the thread is fresh and never seen again,
    which is the stateless behaviour of before, at the cost of one unreferenced
    checkpoint row.
    """
    if not chat_id:
        return f"{identity.user_id}:ephemeral:{uuid.uuid4().hex}"
    return f"{identity.user_id}:{chat_id.strip()[:128]}"


async def _thread_has_history(agent: Any, config: dict) -> bool:
    """Whether the checkpointer already holds this conversation.

    Decides how much of the client's message list to feed the graph. When the
    thread is known, only the latest turn goes in and the checkpoint supplies the
    rest — including the tool calls and results that an OpenAI client never
    sends back, which is the whole reason to keep a thread. When it is not, the
    client's full history is the only history there is: a chat that predates the
    thread, or a checkpoint that was lost.
    """
    try:
        state = await agent.aget_state(config)
    except Exception as exc:
        logger.info("Could not read thread state (%s); treating the thread as new", exc)
        return False
    return bool((state.values or {}).get("messages"))


def _latest_turn(messages: list[dict]) -> list[dict]:
    """The messages after the last assistant reply — the turn being asked now.

    Anything before it is already in the checkpoint. Everything after it is
    sent, so a system message a client prepends to each request still arrives.
    """
    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "assistant":
            return messages[index + 1 :] or messages[-1:]
    return messages


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    prefix = "bearer "
    if header.lower().startswith(prefix):
        return header[len(prefix) :].strip()
    return None


def _guest_id(request: Request) -> str:
    """A stable-enough namespace for one visitor.

    Guests share a namespace per source address rather than getting a fresh one
    per request. What accumulates there is public job postings, so the sharing
    costs no privacy, and the dedupe it enables keeps a curious visitor from
    re-extracting the same vacancies at the owner's expense.
    """
    client = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        client = forwarded.split(",")[0].strip()
    return f"guest:{client}"


def _constant_time_equals(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode(), right.encode())


def main() -> None:
    """Run the shim under uvicorn."""
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    uvicorn.run(
        "scout.server:app",
        host=settings.scout_host,
        port=settings.scout_port,
        log_level="info",
    )
