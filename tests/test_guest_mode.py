"""What a guest run cannot reach.

Phase 1 answered "whose data is this?" with a constant in the settings, which is
correct for one user at a terminal and catastrophic the moment the agent answers
HTTP: one namespace shared by every caller means the first visitor to the
personal page reads the owner's CV.

These tests cover both halves of the fix. The identity has to travel with the
run rather than with the process, and the capabilities that touch the owner's
data have to be absent from a guest agent rather than merely discouraged in its
prompt — an instruction not to use a tool is a request, and the caller is a
stranger.
"""

from __future__ import annotations

import pytest
from deepagents.middleware.filesystem import _check_fs_permission
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from scout.agent import (
    FS_TOOLS,
    FS_TOOLS_READONLY,
    build_private_deny,
    build_subagents,
    build_tools,
)
from scout.config import REPO_ROOT
from scout.identity import Identity, current_identity, current_user_id, run_context


class State(TypedDict):
    seen_user: str
    seen_guest: bool


def identity_probe_graph():
    """A one-node graph that reports the identity it observed while running."""

    def node(state: State) -> State:
        identity = current_identity()
        return {"seen_user": identity.user_id, "seen_guest": identity.is_guest}

    builder = StateGraph(State)
    builder.add_node("probe", node)
    builder.add_edge(START, "probe")
    builder.add_edge("probe", END)
    return builder.compile()


class TestIdentityTravelsWithTheRun:
    async def test_the_run_context_reaches_a_node(self):
        graph = identity_probe_graph()
        result = await graph.ainvoke(
            {"seen_user": "", "seen_guest": False},
            config={"configurable": run_context(Identity("guest:1.2.3.4", is_guest=True))},
        )
        assert result["seen_user"] == "guest:1.2.3.4"
        assert result["seen_guest"] is True

    async def test_two_runs_do_not_share_an_identity(self):
        """The whole point: concurrent callers must not collapse into one namespace."""
        graph = identity_probe_graph()
        first = await graph.ainvoke(
            {"seen_user": "", "seen_guest": False},
            config={"configurable": run_context(Identity("guest:a", is_guest=True))},
        )
        second = await graph.ainvoke(
            {"seen_user": "", "seen_guest": False},
            config={"configurable": run_context(Identity("owner"))},
        )
        assert first["seen_user"] == "guest:a"
        assert second["seen_user"] == "owner"

    def test_outside_a_run_the_configured_user_is_the_honest_answer(self):
        """The CLI and the tests have exactly one user, and it is the owner."""
        assert current_user_id() == "owner"
        assert current_identity().is_guest is False


class TestGuestToolset:
    async def test_a_guest_gets_no_linkedin_tools(self):
        """The burner session is the owner's, and it is bannable."""
        _orchestrator, linkedin = await build_tools(guest=True)
        assert linkedin == []

    @pytest.mark.parametrize("withheld", ["bootstrap_profile", "remember_preference"])
    async def test_a_guest_gets_no_tool_that_writes_owner_memory(self, withheld):
        orchestrator, _ = await build_tools(guest=True)
        assert withheld not in {tool.name for tool in orchestrator}

    async def test_a_guest_can_still_do_the_interesting_part(self):
        """A read-only demo that cannot search is not worth deploying."""
        orchestrator, _ = await build_tools(guest=True)
        assert "research_jobs" in {tool.name for tool in orchestrator}

    def test_a_guest_has_no_cv_writer(self):
        """cv-writer is the one subagent holding the profile and the real contacts."""
        names = {
            spec["name"]
            for spec in build_subagents([], [], backend=None, permissions=[], guest=True)
        }
        assert "cv-writer" not in names
        assert "job-analyst" in names

    def test_the_owner_keeps_cv_writer(self):
        names = {
            spec["name"]
            for spec in build_subagents([], [], backend=None, permissions=[], guest=False)
        }
        assert "cv-writer" in names

    @pytest.mark.parametrize("mutating", ["write_file", "edit_file", "delete", "execute"])
    def test_the_guest_filesystem_cannot_change_anything(self, mutating):
        assert mutating not in FS_TOOLS_READONLY

    def test_the_guest_filesystem_can_still_read_skills(self):
        """Skills are files; without reading them the agent loses its reference material."""
        assert "read_file" in FS_TOOLS_READONLY

    @pytest.mark.parametrize("forbidden", ["delete", "execute"])
    def test_even_the_owner_never_gets_these(self, forbidden):
        assert forbidden not in FS_TOOLS


class TestSecretsAreOutOfReach:
    """The backend is rooted at the repository, and the repository holds .env.

    The agent reads hostile text by design, so "the model would not do that" is
    not a defence: a vacancy description asking it to open .env and quote the
    result is the entire attack.
    """

    @pytest.mark.parametrize(
        "path", [".env", ".env.example", ".git/config", "data/private/cv.pdf"]
    )
    def test_secrets_and_private_data_are_denied(self, path):
        rules = build_private_deny()
        assert _check_fs_permission(rules, "read", str(REPO_ROOT / path)) == "deny"

    @pytest.mark.parametrize("path", [".env", ".git/config"])
    def test_they_cannot_be_written_either(self, path):
        rules = build_private_deny()
        assert _check_fs_permission(rules, "write", str(REPO_ROOT / path)) == "deny"

    @pytest.mark.parametrize(
        "path", ["src/scout/config.py", "skills/writing-cv-content/SKILL.md", "README.md"]
    )
    def test_the_project_itself_stays_readable(self, path):
        rules = build_private_deny()
        assert _check_fs_permission(rules, "read", str(REPO_ROOT / path)) == "allow"
