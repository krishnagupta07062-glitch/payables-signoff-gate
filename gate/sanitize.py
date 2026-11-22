"""Clean untrusted email/invoice text before any model reads it.

Removes what a human reader would not see but a model would: hidden HTML elements, HTML comments,
zero-width and bidi control characters, and Unicode tag characters (U+E0000-E007F, used for invisible
prompt injection). Returns the visible text plus a list of what was removed, for the ledger.
"""
from __future__ import annotations

import html
import re
import unicodedata

_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em)?\b|opacity\s*:\s*0(?:\.0+)?\b"
    r"|color\s*:\s*(?:#fff(?:fff)?|white)\b|max-height\s*:\s*0|height\s*:\s*0(?:px)?\b",
    re.I)
_TAG_BLOCK = re.compile(r"<(script|style|head|template|noscript)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HIDDEN_ELEM = re.compile(
    r"<(?P<tag>[a-z][a-z0-9]*)\b(?P<attrs>[^>]*\b(?:style\s*=\s*(?P<q>[\"'])[^\"']*(?:"
    + _HIDDEN_STYLE.pattern + r")[^\"']*(?P=q)|hidden\b|aria-hidden\s*=\s*[\"']true[\"'])[^>]*)>.*?</(?P=tag)\s*>",
    re.I | re.S)
_BR = re.compile(r"<\s*(br|/p|/div|/tr|/li|/h[1-6])\b[^>]*>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")

# zero-width, bidi controls, word joiner, BOM, soft hyphen
_INVISIBLE = re.compile("[­᠎​-‏‪-‮⁠-⁤⁦-⁩﻿]")
_TAG_CHARS = re.compile("[\U000E0000-\U000E007F]")


def _decode_tag_chars(s: str) -> str:
    """Tag characters mirror ASCII (U+E0041 = 'A'); decode so the ledger shows what was hidden."""
    return "".join(chr(ord(c) - 0xE0000) for c in s if 0xE0020 <= ord(c) <= 0xE007E)


def sanitize(text: str) -> tuple[str, list[str]]:
    """Return (visible_text, removed) where removed describes each hidden item found."""
    removed: list[str] = []
    if not text:
        return "", removed
    s = text

    tag_runs = re.findall("[\U000E0000-\U000E007F]+", s)
    for run in tag_runs:
        removed.append(f"unicode-tag-characters: {_decode_tag_chars(run)[:200]!r}")
    s = _TAG_CHARS.sub("", s)

    n_inv = len(_INVISIBLE.findall(s))
    if n_inv:
        removed.append(f"invisible-characters: {n_inv}")
    s = _INVISIBLE.sub("", s)

    if "<" in s and ">" in s:
        for m in _COMMENT.finditer(s):
            body = m.group(0)[4:-3].strip()
            if body:
                removed.append(f"html-comment: {body[:200]!r}")
        s = _COMMENT.sub("", s)
        for m in _TAG_BLOCK.finditer(s):
            if m.group(1).lower() in ("script", "template", "noscript"):
                removed.append(f"html-{m.group(1).lower()}: {_ANY_TAG.sub('', m.group(0)).strip()[:200]!r}")
        s = _TAG_BLOCK.sub("", s)
        # hidden elements, repeated so nested hidden blocks are caught
        for _ in range(3):
            found = False
            for m in _HIDDEN_ELEM.finditer(s):
                found = True
                inner = _ANY_TAG.sub(" ", m.group(0))
                removed.append(f"hidden-element: {' '.join(inner.split())[:200]!r}")
            s = _HIDDEN_ELEM.sub("", s)
            if not found:
                break
        s = _BR.sub("\n", s)
        s = _ANY_TAG.sub("", s)
        s = html.unescape(s)

    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip(), removed
