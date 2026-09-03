"""CV rendering: Markdown (the source of truth) to Typst to PDF.

The template obeys the rules of the `designing-cv-documents` skill: single
column, semantic elements, 10-11 pt, 25 mm margins, no tables, text boxes, icon
fonts or skill bars. None of that is decoration — it is the condition for the
document surviving the parser on the other end.

This is also the only place where real contact details enter the document.
Prompts and traces hold placeholders such as [EMAIL]; substitution happens at
render time, from a local file, bypassing the model's context entirely.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import tool

from ..config import REPO_ROOT

CONTACTS_PATH = REPO_ROOT / "data" / "private" / "contacts.json"
OUTPUT_DIR = REPO_ROOT / "out"

# PDF tags are on by default from Typst 0.14; --no-pdf-tags is deliberately never passed.
MIN_TYPST_VERSION = (0, 14)

_TYPST_TEMPLATE = """\
#set document(title: {title}, author: {author})
#set page(paper: "a4", margin: 25mm)
#set text(font: "{font}", size: 10.5pt, lang: "{lang}")
#set par(justify: false, leading: 0.6em, spacing: 0.9em)

// Butterick's hierarchy: weight goes to the name, the employers and the roles —
// what the reader is hunting for. The words "EXPERIENCE" and "EDUCATION" are
// navigation furniture and should stay quiet.
// # is the name, ## a section, ### a role/employer.
#show heading.where(level: 1): it => block(
  below: 0.5em,
  text(size: 19pt, weight: "bold", fill: rgb("#111111"), it.body),
)
// Letter-spacing on caps is deliberately NOT used here, although typography
// recommends it: it lands in the extracted text as "EX P ERI ENCE", and section
// headings are exactly what a parser uses to split a CV. Verified by extraction.
#show heading.where(level: 2): it => block(
  above: 1.3em, below: 0.5em,
  text(size: 9.5pt, weight: "semibold", fill: rgb("#1a4d7a"), upper(it.body)),
)
#show heading.where(level: 3): it => block(
  above: 0.9em, below: 0.25em,
  text(size: 11pt, weight: "bold", fill: rgb("#222222"), it.body),
)
#show link: it => text(fill: rgb("#1a4d7a"), it)
#set list(indent: 0.6em, spacing: 0.62em, marker: [•])

{body}
"""


class TypstNotAvailable(RuntimeError):
    """Typst is missing or too old to produce a well-formed PDF."""


def _typst_binary() -> str:
    binary = shutil.which("typst")
    if not binary:
        raise TypstNotAvailable(
            "typst not found. Install it with: brew install typst. "
            "The Markdown version of the CV is already usable and can be sent as is."
        )
    return binary


def typst_version() -> tuple[int, ...]:
    """Return the installed Typst version as a tuple, or (0, 0, 0) if unknown."""
    out = subprocess.run(  # noqa: S603
        [_typst_binary(), "--version"], capture_output=True, text=True, check=False
    ).stdout
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in match.groups()) if match else (0, 0, 0)


def load_contacts() -> dict[str, str]:
    """Load real contacts from the local file. A missing file is not an error."""
    if not CONTACTS_PATH.exists():
        return {}
    try:
        data = json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in data.items() if v}


def substitute_contacts(markdown: str, contacts: dict[str, str] | None = None) -> str:
    """Replace [EMAIL], [PHONE] and similar placeholders with real values.

    Keys in `contacts.json` are written without brackets:
    `{"EMAIL": "...", "PHONE": "..."}`. The [REDACTED_EMAIL] form is supported
    too, because that is what the PII middleware leaves behind; without it a
    placeholder would travel all the way into the finished PDF.
    """
    values = contacts if contacts is not None else load_contacts()
    result = markdown
    for key, value in values.items():
        upper = key.upper()
        result = result.replace(f"[{upper}]", value)
        result = result.replace(f"[REDACTED_{upper}]", value)
    return result


def escape_typst(text: str) -> str:
    """Escape the characters Typst would otherwise read as markup."""
    for char in ("\\", "#", "$", "@", "<", ">", "*", "_", "`", "~"):
        text = text.replace(char, "\\" + char)
    return text


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """Convert inline Markdown to Typst.

    Order matters: marked-up fragments are first stashed behind placeholders,
    then the remainder is escaped, then the markup returns as Typst.
    """
    slots: list[str] = []

    def stash(replacement: str) -> str:
        slots.append(replacement)
        return f"\x00{len(slots) - 1}\x00"

    text = _CODE.sub(lambda m: stash(f'#raw("{m.group(1)}")'), text)
    text = _LINK.sub(lambda m: stash(f'#link("{m.group(2)}")[{escape_typst(m.group(1))}]'), text)
    text = _BOLD.sub(lambda m: stash(f"*{escape_typst(m.group(1))}*"), text)
    text = _ITALIC.sub(lambda m: stash(f"_{escape_typst(m.group(1))}_"), text)

    text = escape_typst(text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


def markdown_to_typst(markdown: str) -> str:
    """Convert the subset of Markdown a CV needs.

    Deliberately narrow: headings, lists, paragraphs, inline markup, rules.
    Tables are absent and will stay absent — CV layout rules forbid them.
    """
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            out.append("")
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            out.append('#line(length: 100%, stroke: 0.5pt + rgb("#cccccc"))')
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 3)
            out.append(f"{'=' * level} {_inline(heading.group(2))}")
            continue

        bullet = re.match(r"^[-*+]\s+(.*)$", stripped)
        if bullet:
            indent = len(line) - len(line.lstrip())
            out.append(f"{' ' * indent}- {_inline(bullet.group(1))}")
            continue

        numbered = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if numbered:
            out.append(f"+ {_inline(numbered.group(2))}")
            continue

        out.append(_inline(stripped))

    return "\n".join(out)


def build_typst_source(
    markdown: str,
    *,
    title: str = "CV",
    author: str = "",
    font: str = "Libertinus Serif",
    lang: str = "en",
) -> str:
    """Assemble the Typst source.

    The default font is Libertinus Serif: it ships with Typst itself, so the
    render is reproducible on any machine, and it covers the Polish diacritics
    (a-ogonek through z-dot: ą ć ę ł ń ó ś ź ż).
    """
    return _TYPST_TEMPLATE.format(
        title=json.dumps(title, ensure_ascii=False),
        author=json.dumps(author, ensure_ascii=False),
        font=font,
        lang=lang,
        body=markdown_to_typst(markdown),
    )


def render_markdown_to_pdf(
    markdown: str,
    output_path: Path | str,
    *,
    title: str = "CV",
    author: str = "",
    lang: str = "en",
    substitute: bool = True,
) -> Path:
    """Render Markdown to PDF and return the path."""
    binary = _typst_binary()
    version = typst_version()
    if version < MIN_TYPST_VERSION:
        raise TypstNotAvailable(
            f"Typst {'.'.join(map(str, version))} is too old: before 0.14 there are no PDF "
            "tags and words fuse across line breaks. Upgrade before using it."
        )

    content = substitute_contacts(markdown) if substitute else markdown
    source = build_typst_source(content, title=title, author=author, lang=lang)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        typ_file = Path(tmp) / "cv.typ"
        typ_file.write_text(source, encoding="utf-8")
        result = subprocess.run(  # noqa: S603
            [
                binary,
                "compile",
                str(typ_file),
                str(destination),
                # Without this the same source renders differently depending on
                # which fonts happen to be installed on the machine.
                "--ignore-system-fonts",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        raise RuntimeError(f"Typst failed to build the PDF: {result.stderr.strip()}")

    return destination


def extract_pdf_text(path: Path | str) -> str:
    """Return the text a parser on the other end will see.

    The only real check of the layout is the one the parsing vendors themselves
    recommend: open the PDF, select all, copy, and read what lands.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@tool
def render_pdf(markdown: str, filename: str = "cv.pdf", language: str = "en") -> str:
    """Render the Markdown CV to PDF and verify that its text extracts.

    Args:
        markdown: the full CV in Markdown. Write contacts as the placeholders
            [EMAIL] and [PHONE]; real values are substituted during rendering.
        filename: name of the output file.
        language: document language code, "en" or "pl".

    Returns:
        The path to the PDF and the result of the extraction check.
    """
    try:
        destination = render_markdown_to_pdf(markdown, OUTPUT_DIR / filename, lang=language)
    except (TypstNotAvailable, RuntimeError) as exc:
        return f"PDF was not built: {exc}"

    extracted = extract_pdf_text(destination)
    words = len(extracted.split())
    warnings: list[str] = []
    if words < 50:
        warnings.append("suspiciously little text extracted from the PDF; check the layout by hand")

    report = f"PDF: {destination}. Extracts {words} words."
    if warnings:
        report += " WARNING: " + "; ".join(warnings)
    return report
