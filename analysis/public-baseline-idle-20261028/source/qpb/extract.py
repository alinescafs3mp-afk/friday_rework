"""Split reasoning from the scored answer and parse that answer only."""

from __future__ import annotations

import re

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_ANSWER_MARKER_RE = re.compile(r"(?i)ANSWER\s*:\s*\**\s*")
_MARKER_LABEL_RE = re.compile(r"[\(\[]?\s*([A-Da-d])\b")
_FINAL_LINE_RE = re.compile(r"^(?:[\(\[]\s*)?([A-Da-d])(?:\s*[\)\]])?$")


def split_final(content: str | None, reasoning_field: str | None = None) -> tuple[str, str | None]:
    """Return (final_answer, reasoning).

    Text inside <think> and a separate reasoning field are not part of the
    scored answer. An empty role delta never arrives here.
    """
    parts: list[str] = []
    if reasoning_field and reasoning_field.strip():
        parts.append(reasoning_field.strip())

    def _grab(match: re.Match) -> str:
        piece = match.group(1).strip()
        if piece:
            parts.append(piece)
        return ""

    final = _THINK_RE.sub(_grab, content or "").strip()
    reasoning = "\n".join(parts) if parts else None
    return final, reasoning


def gpqa_letter(final_text: str | None) -> str | None:
    """Parse a GPQA letter from the final answer only.

    The last ANSWER: marker wins. Without a marker, only a final line that
    is exactly a letter or '(A)'-style label is accepted. An unrecognized
    answer is None. It is not replaced by the last capital in the text.
    """
    text = final_text or ""
    markers = list(_ANSWER_MARKER_RE.finditer(text))
    if markers:
        line = text[markers[-1].end() :].split("\n", 1)[0]
        line = line.strip().strip("*").strip()
        matched = _MARKER_LABEL_RE.match(line)
        if not matched:
            return None
        return matched.group(1).upper()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    matched = _FINAL_LINE_RE.match(lines[-1])
    if not matched:
        return None
    return matched.group(1).upper()


def extract_code(model_output: str | None) -> str:
    """Last fenced block. One program. Not the best of several after tests."""
    lines = (model_output or "").split("\n")
    indexes = [i for i, line in enumerate(lines) if "```" in line]
    if len(indexes) < 2:
        return ""
    return "\n".join(lines[indexes[-2] + 1 : indexes[-1]])
