"""What the tool schemas cost the prompt.

Every tool's JSON schema is re-sent on every turn of the orchestrator loop, so a
verbose schema is not a one-off cost — it is rent, paid per turn, for the whole
run. The stock Tavily search tool exposes nine parameters covering date ranges,
domain allow/deny lists, topic, depth and image toggles; measured against a real
session they came to roughly 1550 tokens a turn, while the query the agent
actually sends came to 19.

These tests pin the narrowed schemas. The failure they are here to catch is a
silent one: a library upgrade rebuilding `args_schema` from the full signature,
restoring the cost with nothing in the diff to show for it.
"""

from __future__ import annotations

import json

import pytest

from scout.config import Settings
from scout.tools.tavily import build_tavily_tools


@pytest.fixture
def tavily_tools(monkeypatch):
    """Tavily tools built against a dummy key; no network is touched."""
    settings = Settings(tavily_api_key="tvly-test-key")
    monkeypatch.setattr("scout.tools.tavily.get_settings", lambda: settings)
    return {tool.name: tool for tool in build_tavily_tools()}


def schema_tokens(tool) -> int:
    """Roughly what the schema costs in the prompt, at four characters a token."""
    blob = json.dumps(
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.args_schema.model_json_schema(),
        },
        ensure_ascii=False,
    )
    return len(blob) // 4


class TestSearchSchema:
    def test_only_the_query_is_exposed(self, tavily_tools):
        properties = tavily_tools["web_search"].args_schema.model_json_schema()["properties"]
        assert list(properties) == ["query"]

    def test_the_schema_stays_cheap(self, tavily_tools):
        assert schema_tokens(tavily_tools["web_search"]) < 300

    @pytest.mark.parametrize(
        "dropped",
        ["start_date", "end_date", "include_domains", "exclude_domains", "include_images"],
    )
    def test_unused_filters_are_gone(self, tavily_tools, dropped):
        properties = tavily_tools["web_search"].args_schema.model_json_schema()["properties"]
        assert dropped not in properties

    def test_the_settings_that_matter_are_pinned_on_the_instance(self, tavily_tools):
        """Narrowing the schema is only safe because these still reach the API.

        `TavilySearch._run` takes every one of them as an optional argument and
        prefers the instance attribute when it is set, so fixing them here costs
        no prompt tokens and cannot be overridden by the model.
        """
        search = tavily_tools["web_search"]
        assert search.search_depth == "basic"
        assert search.topic == "general"
        assert search.include_answer is False
        assert search.include_raw_content is False


class TestExtractSchema:
    def test_only_the_urls_are_exposed(self, tavily_tools):
        properties = tavily_tools["web_extract"].args_schema.model_json_schema()["properties"]
        assert list(properties) == ["urls"]

    def test_the_schema_stays_cheap(self, tavily_tools):
        assert schema_tokens(tavily_tools["web_extract"]) < 200

    def test_extraction_depth_is_pinned_on_the_instance(self, tavily_tools):
        assert tavily_tools["web_extract"].extract_depth == "basic"


class TestDegradedMode:
    def test_no_key_means_no_tools(self, monkeypatch):
        """A missing key drops the tools rather than failing the run."""
        monkeypatch.setattr("scout.tools.tavily.get_settings", lambda: Settings(tavily_api_key=None))
        assert build_tavily_tools() == []
