"""What the HTTP shim lets through.

The shim is the first piece of this project reachable from outside the machine,
so its tests are about refusal rather than about function. The failures that
matter here are the quiet ones: an unset token that silently means "everybody
in", a guest handed the owner's agent because the client asked for it by name,
a subagent's working notes typed into a stranger's chat window.

Lifespan is deliberately not run. `TestClient` only executes it when used as a
context manager, so the agents can be replaced with fakes and no test needs an
API key, a database or the LinkedIn MCP process.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from scout.config import Settings
from scout.identity import Identity
from scout.server import (
    GUEST_MODEL,
    OWNER_MODEL,
    RateLimiter,
    _is_user_facing,
    _to_langchain,
    app,
    registry,
)

OWNER_TOKEN = "owner-secret"
GUEST_TOKEN = "guest-public"


class FakeAgent:
    """Stands in for a built agent, recording the config it was run with."""

    def __init__(self, reply: str = "answer") -> None:
        self.reply = reply
        self.configs: list[dict] = []

    async def ainvoke(self, payload, config=None):
        self.configs.append(config or {})
        return {"messages": [AIMessage(content=self.reply)]}

    async def astream(self, payload, config=None, stream_mode=None):
        self.configs.append(config or {})
        top = {"langgraph_node": "model", "checkpoint_ns": "model:abc"}
        nested = {"langgraph_node": "model", "checkpoint_ns": "task:1|model:2"}
        yield AIMessageChunk(content="Hello"), top
        yield AIMessageChunk(content=" there"), top
        # A subagent thinking out loud; it must not reach the client.
        yield AIMessageChunk(content="SUBAGENT NOTES"), nested


@pytest.fixture
def agents(monkeypatch):
    owner, guest = FakeAgent("owner reply"), FakeAgent("guest reply")
    monkeypatch.setattr(registry, "owner", owner, raising=False)
    monkeypatch.setattr(registry, "guest", guest, raising=False)
    return owner, guest


@pytest.fixture
def configure(monkeypatch):
    """Point the shim's settings lookup at a purpose-built Settings."""

    def apply(**kwargs):
        defaults = {"scout_owner_token": OWNER_TOKEN, "scout_user_id": "owner"}
        settings = Settings(**{**defaults, **kwargs})
        monkeypatch.setattr("scout.server.get_settings", lambda: settings)
        return settings

    return apply


@pytest.fixture
def client():
    return TestClient(app)


def post(client, token=None, **body):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {"messages": [{"role": "user", "content": "hi"}], **body}
    return client.post("/v1/chat/completions", json=payload, headers=headers)


class TestAuthentication:
    def test_an_unset_owner_token_closes_the_door_rather_than_opening_it(
        self, client, configure, agents
    ):
        """The dangerous default would be to treat "no token" as "no auth needed"."""
        configure(scout_owner_token=None)
        assert post(client, OWNER_TOKEN).status_code == 503

    def test_a_wrong_token_is_refused(self, client, configure, agents):
        configure()
        assert post(client, "not-the-token").status_code == 401

    def test_a_missing_token_is_refused(self, client, configure, agents):
        configure()
        assert post(client).status_code == 401

    def test_the_owner_token_is_accepted(self, client, configure, agents):
        configure()
        response = post(client, OWNER_TOKEN)
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "owner reply"

    def test_guests_are_refused_while_guest_access_is_off(self, client, configure, agents):
        configure(scout_guest_enabled=False, scout_guest_token=GUEST_TOKEN)
        assert post(client, GUEST_TOKEN).status_code == 401

    def test_the_guest_token_is_accepted_once_guest_access_is_on(self, client, configure, agents):
        configure(scout_guest_enabled=True, scout_guest_token=GUEST_TOKEN)
        response = post(client, GUEST_TOKEN)
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "guest reply"


class TestIdentityRouting:
    def test_a_guest_asking_for_the_owner_model_still_gets_the_guest_agent(
        self, client, configure, agents
    ):
        """The model name comes from the client and is not a credential."""
        configure(scout_guest_enabled=True, scout_guest_token=GUEST_TOKEN)
        owner, _guest = agents
        response = post(client, GUEST_TOKEN, model=OWNER_MODEL)
        assert response.json()["choices"][0]["message"]["content"] == "guest reply"
        assert owner.configs == []

    def test_the_guest_flag_travels_into_the_run(self, client, configure, agents):
        """Memory namespacing and the in-tool guards both read this."""
        configure(scout_guest_enabled=True, scout_guest_token=GUEST_TOKEN)
        _owner, guest = agents
        post(client, GUEST_TOKEN)
        configurable = guest.configs[0]["configurable"]
        assert configurable["is_guest"] is True
        assert configurable["user_id"].startswith("guest:")

    def test_the_owner_runs_under_the_configured_user_id(self, client, configure, agents):
        configure(scout_user_id="owner")
        owner, _guest = agents
        post(client, OWNER_TOKEN)
        assert owner.configs[0]["configurable"] == {"user_id": "owner", "is_guest": False}

    def test_a_guest_is_not_shown_the_owner_model(self, client, configure, agents):
        configure(scout_guest_enabled=True, scout_guest_token=GUEST_TOKEN)
        response = client.get("/v1/models", headers={"Authorization": f"Bearer {GUEST_TOKEN}"})
        assert [m["id"] for m in response.json()["data"]] == [GUEST_MODEL]

    def test_the_owner_sees_both_models(self, client, configure, agents):
        configure()
        response = client.get("/v1/models", headers={"Authorization": f"Bearer {OWNER_TOKEN}"})
        assert [m["id"] for m in response.json()["data"]] == [OWNER_MODEL, GUEST_MODEL]


class TestStreaming:
    def test_the_stream_is_openai_shaped_and_terminated(self, client, configure, agents):
        configure()
        response = post(client, OWNER_TOKEN, stream=True)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.text.rstrip().endswith("data: [DONE]")

    def test_the_answer_arrives_in_deltas(self, client, configure, agents):
        configure()
        body = post(client, OWNER_TOKEN, stream=True).text
        text = "".join(
            json.loads(line[6:])["choices"][0]["delta"].get("content", "")
            for line in body.splitlines()
            if line.startswith("data: ") and not line.endswith("[DONE]")
        )
        assert text == "Hello there"

    def test_subagent_chatter_never_reaches_the_client(self, client, configure, agents):
        """Subagents exist to keep their working context out of the conversation."""
        configure()
        assert "SUBAGENT NOTES" not in post(client, OWNER_TOKEN, stream=True).text


class TestChunkFilter:
    def test_a_nested_namespace_is_a_subagent(self):
        meta = {"langgraph_node": "model", "checkpoint_ns": "task:1|model:2"}
        assert not _is_user_facing(AIMessageChunk(content="x"), meta)

    def test_the_orchestrator_model_passes(self):
        meta = {"langgraph_node": "model", "checkpoint_ns": "model:abc"}
        assert _is_user_facing(AIMessageChunk(content="x"), meta)

    def test_other_nodes_are_machinery(self):
        meta = {"langgraph_node": "tools", "checkpoint_ns": "tools:abc"}
        assert not _is_user_facing(AIMessageChunk(content="x"), meta)


class TestRateLimit:
    def test_the_hourly_ceiling_holds(self):
        limiter = RateLimiter(per_hour=3, per_day=100)
        assert [limiter.check("a") for _ in range(3)] == [None, None, None]
        assert "Hourly limit" in (limiter.check("a") or "")

    def test_the_daily_ceiling_holds(self):
        limiter = RateLimiter(per_hour=100, per_day=2)
        limiter.check("a"), limiter.check("a")
        assert "Daily limit" in (limiter.check("a") or "")

    def test_visitors_are_counted_separately(self):
        limiter = RateLimiter(per_hour=1, per_day=10)
        assert limiter.check("a") is None
        assert limiter.check("b") is None

    def test_the_shim_refuses_over_the_limit(self, client, configure, agents, monkeypatch):
        configure()
        monkeypatch.setattr("scout.server.limiter", RateLimiter(per_hour=1, per_day=10))
        assert post(client, OWNER_TOKEN).status_code == 200
        assert post(client, OWNER_TOKEN).status_code == 429


class TestMessageTranslation:
    def test_roles_without_a_counterpart_are_remapped(self):
        messages = _to_langchain(
            [
                type("M", (), {"role": "developer", "content": "sys"})(),
                type("M", (), {"role": "tool", "content": "result"})(),
            ]
        )
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_empty_messages_are_dropped(self):
        assert _to_langchain([type("M", (), {"role": "user", "content": None})()]) == []

    def test_content_blocks_are_flattened(self):
        blocks = [{"type": "text", "text": "a"}, {"type": "image_url", "image_url": {}}]
        message = type("M", (), {"role": "user", "content": blocks})()
        assert _to_langchain([message]) == [{"role": "user", "content": "a"}]

    def test_a_request_with_nothing_to_answer_is_rejected(self, client, configure, agents):
        configure()
        response = client.post(
            "/v1/chat/completions",
            json={"messages": []},
            headers={"Authorization": f"Bearer {OWNER_TOKEN}"},
        )
        assert response.status_code == 400


class TestHealth:
    def test_health_needs_no_token(self, client, configure, agents):
        configure()
        assert client.get("/health").status_code == 200


class TestIdentityCapabilities:
    def test_a_guest_may_not_read_the_owner_profile(self):
        assert Identity("guest:1", is_guest=True).may_read_owner_profile is False

    def test_a_guest_may_not_write(self):
        assert Identity("guest:1", is_guest=True).may_write is False

    def test_the_owner_may(self):
        owner = Identity("owner")
        assert owner.may_read_owner_profile and owner.may_write
