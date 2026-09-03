"""Tests for the CV renderer.

The main check is the one the parsing vendors recommend: build the PDF, extract
its text and read what came out. A document that looks good on screen but
extracts as garbage is a failure, not a matter of taste.
"""

from __future__ import annotations

import shutil

import pytest

from scout.tools.render_pdf import (
    escape_typst,
    extract_pdf_text,
    markdown_to_typst,
    render_markdown_to_pdf,
    substitute_contacts,
)

typst_required = pytest.mark.skipif(shutil.which("typst") is None, reason="typst is not installed")

SAMPLE_CV = """\
# Jan Kowalski

Warsaw, Poland | [EMAIL] | [PHONE]

Backend engineer with 8 years in Python and Go.

## Professional Experience

### Senior Backend Engineer — Acme Sp. z o.o.
*01/2021 — present*

- Built a **retrieval-augmented generation** (RAG) pipeline over 400k documents.
- Ran production workloads on Kubernetes across 12 services.
- Polish diacritics: ąćęłńóśźż ĄĆĘŁŃÓŚŹŻ

## Education

### MSc Computer Science — Politechnika Warszawska
"""


class TestMarkdownConversion:
    def test_headings_become_typst_headings(self):
        assert markdown_to_typst("# Name").startswith("= Name")
        assert markdown_to_typst("## Section").startswith("== Section")
        assert markdown_to_typst("### Role").startswith("=== Role")

    def test_bullets_are_preserved(self):
        assert markdown_to_typst("- item").strip().startswith("- item")

    def test_bold_and_italic(self):
        assert "*bold*" in markdown_to_typst("**bold**")
        assert "_italic_" in markdown_to_typst("*italic*")

    def test_links_become_typst_links(self):
        result = markdown_to_typst("[text](https://example.com)")
        assert '#link("https://example.com")' in result

    def test_special_characters_are_escaped(self):
        """Typst markup characters in ordinary text must not break the build."""
        assert escape_typst("C# and $100 @ home") == "C\\# and \\$100 \\@ home"

    def test_plain_text_with_hash_does_not_become_heading(self):
        result = markdown_to_typst("Grade: A#1 result")
        assert not result.startswith("=")


class TestContactSubstitution:
    def test_placeholders_are_replaced(self):
        result = substitute_contacts("[EMAIL] and [PHONE]", {"EMAIL": "a@b.c", "PHONE": "+48"})
        assert result == "a@b.c and +48"

    def test_redacted_form_is_also_replaced(self):
        """The PII middleware leaves [REDACTED_EMAIL], which must be substituted too."""
        result = substitute_contacts("[REDACTED_EMAIL]", {"EMAIL": "a@b.c"})
        assert result == "a@b.c"

    def test_missing_contacts_leave_placeholder_visible(self):
        assert substitute_contacts("[EMAIL]", {}) == "[EMAIL]"


@typst_required
class TestPdfRendering:
    @pytest.fixture
    def pdf_text(self, tmp_path) -> str:
        path = render_markdown_to_pdf(SAMPLE_CV, tmp_path / "cv.pdf", substitute=False)
        assert path.exists() and path.stat().st_size > 1000
        return extract_pdf_text(path)

    def test_text_is_extractable(self, pdf_text):
        assert len(pdf_text.split()) > 30

    def test_reading_order_is_preserved(self, pdf_text):
        """Name before experience, experience before education, as in the source."""
        assert pdf_text.index("Jan Kowalski") < pdf_text.index("Acme")
        assert pdf_text.index("Acme") < pdf_text.index("Politechnika")

    def test_section_headings_survive_as_whole_words(self, pdf_text):
        """Letter-spacing on caps would tear words apart: EX P ERI ENCE."""
        assert "PROFESSIONAL EXPERIENCE" in pdf_text
        assert "EDUCATION" in pdf_text

    def test_polish_diacritics_survive(self, pdf_text):
        assert "ąćęłńóśźż" in pdf_text
        assert "ĄĆĘŁŃÓŚŹŻ" in pdf_text

    def test_words_are_not_fused_across_line_breaks(self, pdf_text):
        assert "retrieval-augmented generation" in pdf_text

    def test_contact_line_is_in_the_body(self, pdf_text):
        """Contacts must live in the document body, not in a header or footer."""
        assert "Warsaw, Poland" in pdf_text
