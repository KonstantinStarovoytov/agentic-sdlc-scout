"""Reading a posting out of what `get_job_details` actually returns.

The shapes here are copied from a real answer of mcp-server-linkedin 4.23.3: a
list of MCP content blocks whose `text` holds a JSON document, with the posting
under `sections.job_posting`. Stringifying that list was the original behaviour
and it is what these guard against.
"""

from __future__ import annotations

import json

from scout.tools.linkedin_mcp import job_description_from

POSTING = (
    "Senior AI Engineer\n\nAbout the job\n\nRequirements\n\n"
    "At least 5 years of commercial experience.\nStrong Python skills.\n"
)


def _blocks(payload: dict) -> list[dict]:
    return [{"type": "text", "text": json.dumps(payload), "id": "lc_bc03e6f8"}]


class TestRealPayload:
    def test_the_posting_is_unwrapped_from_the_content_block(self):
        raw = _blocks(
            {"url": "https://www.linkedin.com/jobs/view/1/", "sections": {"job_posting": POSTING}}
        )
        assert job_description_from(raw) == POSTING

    def test_the_wrapper_does_not_reach_the_model(self):
        """The repr of the block list used to be the description verbatim."""
        raw = _blocks({"sections": {"job_posting": POSTING}})
        result = job_description_from(raw)
        assert "'type': 'text'" not in result
        assert "lc_bc03e6f8" not in result
        assert "sections" not in result

    def test_unwrapping_is_what_keeps_the_length_cap_honest(self):
        """The cap in the extract node measures this string, so it must be the posting.

        With the wrapper included, a long posting spends its budget on escaped
        JSON and the requirements — which sit late in a description — are the
        part that gets cut.
        """
        long_posting = POSTING + ("Kubernetes, Terraform, LangGraph. " * 400)
        raw = _blocks({"sections": {"job_posting": long_posting}})
        result = job_description_from(raw)
        assert len(result) == len(long_posting)
        assert result[:12000].endswith("LangGraph. ") or "Requirements" in result[:12000]


class TestOtherShapes:
    def test_a_plain_string_is_passed_through(self):
        assert job_description_from(POSTING) == POSTING

    def test_a_block_object_is_read_like_a_dict(self):
        class Block:
            text = json.dumps({"sections": {"job_posting": POSTING}})

        assert job_description_from([Block()]) == POSTING

    def test_non_json_text_survives(self):
        assert job_description_from([{"type": "text", "text": POSTING}]) == POSTING

    def test_a_description_key_is_accepted_when_there_are_no_sections(self):
        assert job_description_from(_blocks({"description": POSTING})) == POSTING

    def test_an_empty_posting_falls_back_rather_than_returning_nothing(self):
        """A blank section must not silently become an empty description."""
        raw = _blocks({"sections": {"job_posting": "  "}, "description": POSTING})
        assert job_description_from(raw) == POSTING

    def test_an_unknown_shape_is_not_dropped(self):
        assert "42" in job_description_from(42)

    def test_multiple_blocks_are_joined(self):
        raw = [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]
        assert job_description_from(raw) == "first\nsecond"
