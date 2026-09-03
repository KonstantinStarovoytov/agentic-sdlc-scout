"""Which CV file formats the ingest actually accepts.

`.doc` was routed to python-docx, which reads the OOXML container only. The
owner sees a stack trace out of a zip parser instead of being told to save the
file as something readable, and the difference matters because this is the first
tool anyone runs.
"""

from __future__ import annotations

import pytest

from scout.tools.profile_ingest import extract_text_from_file


class TestUnsupportedFormats:
    def test_legacy_doc_gets_the_tools_own_message(self, tmp_path):
        path = tmp_path / "cv.doc"
        path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")  # OLE2 magic

        with pytest.raises(ValueError, match="Unsupported format"):
            extract_text_from_file(path)

    def test_the_message_says_what_would_work(self, tmp_path):
        path = tmp_path / "cv.doc"
        path.write_bytes(b"\xd0\xcf\x11\xe0")

        with pytest.raises(ValueError) as excinfo:
            extract_text_from_file(path)
        assert "DOCX" in str(excinfo.value)

    @pytest.mark.parametrize("suffix", [".rtf", ".odt", ".pages", ""])
    def test_other_unknown_formats_behave_the_same(self, tmp_path, suffix):
        path = tmp_path / f"cv{suffix}"
        path.write_bytes(b"x")

        with pytest.raises(ValueError, match="Unsupported format"):
            extract_text_from_file(path)

    def test_a_missing_file_is_a_different_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_text_from_file(tmp_path / "absent.pdf")


class TestSupportedFormats:
    @pytest.mark.parametrize("suffix", [".md", ".txt"])
    def test_plain_text_is_read_as_is(self, tmp_path, suffix):
        path = tmp_path / f"cv{suffix}"
        path.write_text("Senior AI Engineer", encoding="utf-8")
        assert extract_text_from_file(path) == "Senior AI Engineer"

    def test_the_extension_is_matched_case_insensitively(self, tmp_path):
        path = tmp_path / "CV.TXT"
        path.write_text("Senior AI Engineer", encoding="utf-8")
        assert extract_text_from_file(path) == "Senior AI Engineer"
