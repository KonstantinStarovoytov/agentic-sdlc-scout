"""The owner's personal data must not travel into traces.

Redaction applies to user input only. Tool results carry other people's
contacts inside untrusted text, and rewriting them would damage the very
material the agent is meant to analyse — see `build_pii_middleware` for the
full reasoning.

Phone and email from the CV exist as placeholders in prompts; the real values are
substituted only when the PDF is rendered, from a local file (see
`tools/render_pdf.py`).

The email detector is the stock one from langchain; the phone pattern is written
here because there is no built-in type for it, and Polish plus international
formats are exactly what will appear in the owner's CV.
"""

from __future__ import annotations

import re

from langchain.agents.middleware import AgentMiddleware, PIIMiddleware

# +48 601 234 567, 601-234-567, (22) 123 45 67, +1 415 555 0132
PHONE_PATTERN = (
    r"(?:(?:\+|00)\d{1,3}[\s.-]?)?"
    r"(?:\(\d{1,4}\)[\s.-]?)?"
    r"\d{2,4}(?:[\s.-]?\d{2,4}){1,3}"
)

EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

_EMAIL_RE = re.compile(EMAIL_PATTERN)
# Searching free text needs a stricter phone pattern: otherwise years, versions
# and volumes such as "400k" or "2021 - 2024" match it.
_PHONE_RE = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s.-]?)(?:\(\d{1,4}\)[\s.-]?)?\d{2,4}(?:[\s.-]?\d{2,4}){1,3}"
    r"|(?<!\d)\d{3}[\s.-]\d{3}[\s.-]\d{3}(?!\d)"
)


def redact_contacts(text: str) -> tuple[str, dict[str, str]]:
    """Replace email and phone with placeholders and return what was found.

    Needed wherever a model is called directly, bypassing middleware — above all
    when parsing the CV. Afterwards the real contacts live only in a local file
    and are substituted when the PDF is rendered.
    """
    found: dict[str, str] = {}

    emails = _EMAIL_RE.findall(text)
    if emails:
        found["EMAIL"] = emails[0]
        text = _EMAIL_RE.sub("[EMAIL]", text)

    phones = _PHONE_RE.findall(text)
    if phones:
        found["PHONE"] = phones[0].strip()
        text = _PHONE_RE.sub("[PHONE]", text)

    return text, found


def build_pii_middleware() -> list[AgentMiddleware]:
    """Redact email and phone in user input. Tool results are left untouched.

    The asymmetry is intentional. User input is where the owner's own contacts
    appear, and those must not reach a provider or a trace. Tool results are the
    untrusted side: they are job descriptions, company pages and profiles, whose
    contacts belong to other people and are part of the text being analysed.
    Redacting them would corrupt the material the rubric reads and destroy the
    recruiter address the user needs in order to apply.

    URLs are deliberately left alone: links to a posting and to a profile are
    working data, without which the agent can neither cite a source nor open a
    description.
    """
    return [
        PIIMiddleware(
            "email",
            strategy="redact",
            apply_to_input=True,
            apply_to_tool_results=False,
        ),
        PIIMiddleware(
            "phone",
            detector=PHONE_PATTERN,
            strategy="redact",
            apply_to_input=True,
            apply_to_tool_results=False,
        ),
    ]
