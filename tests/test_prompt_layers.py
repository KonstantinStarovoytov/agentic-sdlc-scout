"""What the prompt layers promise the user.

A prompt that offers a capability the code does not have is worse than a silent
gap: the user asks for it, the agent tries, and the failure lands on the agent's
credibility rather than on the missing feature.
"""

from __future__ import annotations

from scout.config import ScoutConfig
from scout.middleware.pii import build_pii_middleware
from scout.prompts import (
    CV_WRITER_PROMPT,
    JOB_ANALYST_PROMPT,
    build_system_prompt,
    taxonomy_layer,
)


class TestTaxonomyLayer:
    def test_the_empty_layer_does_not_advertise_a_missing_mode(self):
        """bootstrap_taxonomy is out of scope for phase 1 and does not exist."""
        assert "bootstrap_taxonomy" not in taxonomy_layer(None)

    def test_the_empty_layer_points_at_tools_that_exist(self):
        text = taxonomy_layer(None)
        assert "research_jobs" in text and "gap_analysis" in text

    def test_the_empty_layer_still_forbids_answering_from_model_memory(self):
        assert "memory" in taxonomy_layer(None)

    def test_a_populated_taxonomy_is_rendered_from_the_data(self):
        text = taxonomy_layer(
            {"sample_size": 40, "demands": [{"skill": "LangGraph", "tier": "core", "share": 0.6}]}
        )
        assert "LangGraph" in text and "60%" in text

    def test_the_full_prompt_never_mentions_the_missing_mode(self):
        assert "bootstrap_taxonomy" not in build_system_prompt(None, ScoutConfig())


class TestSubagentPrompts:
    def test_job_analyst_is_pointed_at_a_tool_it_owns(self):
        assert "read_job_dossier" in JOB_ANALYST_PROMPT

    def test_cv_writer_is_pointed_at_a_tool_it_owns(self):
        assert "read_job_dossier" in CV_WRITER_PROMPT

    def test_cv_writer_is_warned_the_dossier_is_untrusted(self):
        assert "untrusted" in CV_WRITER_PROMPT.lower()

    def test_the_iron_rule_names_the_tool_that_enforces_it(self):
        """The rule used to cite a document the subagent had no way to open."""
        assert "Candidate Profile is not in the document" in CV_WRITER_PROMPT
        assert "read_candidate_profile" in CV_WRITER_PROMPT


class TestPIIScope:
    def test_redaction_is_input_only(self):
        """Tool results carry other people's contacts inside the text being analysed."""
        middleware = build_pii_middleware()
        assert middleware
        for entry in middleware:
            assert entry.apply_to_input is True
            assert entry.apply_to_tool_results is False

    def test_the_documented_scope_matches_the_configuration(self):
        """The docstring used to claim tool results were redacted too."""
        doc = build_pii_middleware.__doc__ or ""
        assert "input" in doc.lower()
        assert "left untouched" in doc.lower()
