"""取得文字列のクリーニング。

HTMLタグを除去し、空白を正規化、長さを切り詰める。
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .config import BODY_MAX_CHARS

_WHITESPACE = re.compile(r"\s+")


def clean_text(raw: str | None, max_chars: int = BODY_MAX_CHARS) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = _WHITESPACE.sub(" ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text
