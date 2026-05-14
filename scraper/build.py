"""Jinja2 で docs/ 配下に静的HTMLを生成する。

セキュリティ:
- autoescape = select_autoescape(["html", "xml"]) でXSS対策デフォルトON
- |safe フィルタは絶対に使わない（base.html.j2側でも禁止）
- 全テキストは sanitize.clean_text を通したものを渡す
- JSON-LD は |tojson 経由で安全にエスケープ
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import (
    DATA_FILE,
    DOCS_DIR,
    REPO_URL,
    SITE_DESCRIPTION,
    SITE_NAME,
    SITE_URL,
    TEMPLATES_DIR,
    WORKER_URL,
)
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
        "plain_summary": clean_text(record.get("plain_summary", ""), max_chars=140),
        "body": clean_text(record.get("body", ""), max_chars=2500),
        "target_text": clean_text(record.get("target_text", ""), max_chars=200),
        "amount_text": clean_text(record.get("amount_text", ""), max_chars=100),
        "prefecture": clean_text(record.get("prefecture", ""), max_chars=20),
        "catch_phrase": clean_text(record.get("catch_phrase", ""), max_chars=200),
        "subsidy_rate_official": clean_text(record.get("subsidy_rate_official", ""), max_chars=50),
    }


def _build_index_ld(subsidies: list[dict]) -> dict:
    """トップページ用 JSON-LD: WebSite + ItemList。"""
    items = []
    for i, s in enumerate(subsidies, 1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "url": f"{SITE_URL}/subsidies/{s['id']}.html",
            "name": s.get("title", ""),
        })
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": SITE_NAME,
                "url": f"{SITE_URL}/",
                "description": SITE_DESCRIPTION,
                "inLanguage": "ja",
            },
            {
                "@type": "ItemList",
                "name": f"{SITE_NAME} 補助金一覧",
                "numberOfItems": len(items),
                "itemListElement": items[:100],  # 検索エンジン向け、長すぎ防止
            },
        ],
    }


def _build_detail_ld(s: dict) -> dict:
    """詳細ページ用 JSON-LD: Article。"""
    description = s.get("plain_summary") or s.get("catch_phrase") or ""
    data: dict = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": s.get("title", ""),
        "description": description,
        "inLanguage": "ja",
        "url": f"{SITE_URL}/subsidies/{s['id']}.html",
        "isAccessibleForFree": True,
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": f"{SITE_URL}/",
        },
    }
    if s.get("first_seen_at"):
        data["datePublished"] = s["first_seen_at"]
    if s.get("updated_at"):
        data["dateModified"] = s["updated_at"]
    if s.get("source"):
        data["sourceOrganization"] = {
            "@type": "GovernmentOrganization",
            "name": "デジタル庁",
        }
    return data


def _build_sitemap_xml(subsidies: list[dict], updated_at_iso: str) -> str:
    """sitemap.xml を組み立てる。"""
    lastmod = updated_at_iso[:10] if updated_at_iso else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        (f"{SITE_URL}/", "daily", "1.0"),
        (f"{SITE_URL}/about.html", "monthly", "0.5"),
        (f"{SITE_URL}/privacy.html", "yearly", "0.3"),
    ]
    for s in subsidies:
        urls.append((f"{SITE_URL}/subsidies/{s['id']}.html", "daily", "0.7"))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, changefreq, priority in urls:
        # URL構成要素は安全 (英数字+ハイフン+ASCII) なので追加エスケープ不要
        lines.append("  <url>")
        lines.append(f"    <loc>{url}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines)


def _build_robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )


def _share_text(s: dict) -> str:
    """Twitter Web Intent の text パラメータ用。URLエンコード済み。"""
    parts = [s.get("title", "")]
    if s.get("plain_summary"):
        parts.append(s["plain_summary"])
    parts.append(f"#補助金まとめ")
    raw = "\n".join(p for p in parts if p)
    # Twitterのtext上限は控えめに 200 文字程度
    if len(raw) > 200:
        raw = raw[:197] + "..."
    return quote(raw, safe="")


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

    worker_origin = ""
    if WORKER_URL:
        parsed = urlparse(WORKER_URL)
        if parsed.scheme == "https" and parsed.netloc:
            worker_origin = f"https://{parsed.netloc}"

    common = {
        "updated_at": updated_display,
        "repo_url": REPO_URL,
        "worker_url": WORKER_URL,
        "worker_origin": worker_origin,
        "site_url": SITE_URL,
        "site_name": SITE_NAME,
        "site_description": SITE_DESCRIPTION,
    }

    index_tmpl = env.get_template("index.html.j2")
    (DOCS_DIR / "index.html").write_text(
        index_tmpl.render(
            subsidies=subsidies,
            total=total,
            index_ld_data=_build_index_ld(subsidies),
            **common,
        ),
        encoding="utf-8",
    )

    about_tmpl = env.get_template("about.html.j2")
    (DOCS_DIR / "about.html").write_text(
        about_tmpl.render(total=total, **common),
        encoding="utf-8",
    )

    privacy_tmpl = env.get_template("privacy.html.j2")
    (DOCS_DIR / "privacy.html").write_text(
        privacy_tmpl.render(**common),
        encoding="utf-8",
    )

    not_found_tmpl = env.get_template("404.html.j2")
    (DOCS_DIR / "404.html").write_text(
        not_found_tmpl.render(**common),
        encoding="utf-8",
    )

    detail_tmpl = env.get_template("detail.html.j2")
    for s in subsidies:
        share_url = f"{SITE_URL}/subsidies/{s['id']}.html"
        (DOCS_DIR / "subsidies" / f"{s['id']}.html").write_text(
            detail_tmpl.render(
                s=s,
                detail_ld_data=_build_detail_ld(s),
                share_url=share_url,
                share_tweet_text=_share_text(s),
                **common,
            ),
            encoding="utf-8",
        )

    (DOCS_DIR / "sitemap.xml").write_text(
        _build_sitemap_xml(subsidies, updated_at_iso),
        encoding="utf-8",
    )
    (DOCS_DIR / "robots.txt").write_text(_build_robots_txt(), encoding="utf-8")

    logger.info("build: index + detail %d ページ + 404 + sitemap.xml + robots.txt を生成", total)
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
