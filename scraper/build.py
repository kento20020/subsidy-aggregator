"""Jinja2 で docs/ 配下に静的HTMLを生成する。

セキュリティ:
- autoescape = select_autoescape(["html", "xml"]) でXSS対策デフォルトON
- |safe フィルタは絶対に使わない（base.html.j2側でも禁止）
- 全テキストは sanitize.clean_text を通したものを渡す
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import DATA_FILE, DOCS_DIR, REPO_URL, TEMPLATES_DIR
from .sanitize import clean_text

logger = logging.getLogger(__name__)


def _build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _prepare_view(record: dict) -> dict:
    """テンプレート渡し前のクリーニング。"""
    return {
        **record,
        "title": clean_text(record.get("title", ""), max_chars=200),
        "summary": clean_text(record.get("summary", ""), max_chars=400),
        "body": clean_text(record.get("body", ""), max_chars=1500),
        "target_text": clean_text(record.get("target_text", ""), max_chars=200),
        "amount_text": clean_text(record.get("amount_text", ""), max_chars=100),
        "prefecture": clean_text(record.get("prefecture", ""), max_chars=20),
    }


def run() -> int:
    if not DATA_FILE.exists():
        logger.error("data/subsidies.json が存在しません。")
        return 1

    state = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    subsidies = [_prepare_view(s) for s in state.get("subsidies", [])]

    subsidies.sort(
        key=lambda s: (s.get("first_seen_at") or ""),
        reverse=True,
    )

    env = _build_env()
    updated_at_iso = state.get("updated_at") or datetime.now(timezone.utc).isoformat()
    updated_display = _format_jst(updated_at_iso)
    total = len(subsidies)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    # 削除された補助金の旧HTMLや旧テンプレートで生成された残骸を防ぐため毎回ワイプ
    subsidies_dir = DOCS_DIR / "subsidies"
    if subsidies_dir.exists():
        shutil.rmtree(subsidies_dir)
    subsidies_dir.mkdir(parents=True, exist_ok=True)

    common = {"updated_at": updated_display, "repo_url": REPO_URL}

    index_tmpl = env.get_template("index.html.j2")
    (DOCS_DIR / "index.html").write_text(
        index_tmpl.render(subsidies=subsidies, total=total, **common),
        encoding="utf-8",
    )

    about_tmpl = env.get_template("about.html.j2")
    (DOCS_DIR / "about.html").write_text(
        about_tmpl.render(total=total, **common),
        encoding="utf-8",
    )

    detail_tmpl = env.get_template("detail.html.j2")
    for s in subsidies:
        (DOCS_DIR / "subsidies" / f"{s['id']}.html").write_text(
            detail_tmpl.render(s=s, **common),
            encoding="utf-8",
        )

    logger.info("build: index + detail %d ページを生成", total)
    return 0


def _format_jst(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run()


if __name__ == "__main__":
    sys.exit(main())
