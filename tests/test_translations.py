"""Checks for the translation files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "charge_ahead"
FILES = [
    COMPONENT / "strings.json",
    *sorted((COMPONENT / "translations").glob("*.json")),
]


def _strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, str):
        yield node


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_literal_template_braces(path: Path) -> None:
    """The frontend parses strings as ICU messages; '{{' breaks them."""
    for text in _strings(json.loads(path.read_text(encoding="utf-8"))):
        assert "{{" not in text, text
