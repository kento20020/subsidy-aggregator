"""robots.txt を取得し、自動アクセス先（APIホスト）が許可されているか確認する。

- 自動取得するのは API ホスト（api.jgrants-portal.go.jp）のみ
- 詳細ページの www.jgrants-portal.go.jp は外部リンクとして貼るだけで自動アクセスしない
- robots.txt が404の場合はRFC 9309に基づき「制限なし」と解釈
- 結果は docs/robots_check.md に追記。違反検出時は False を返し、呼び出し側が停止する。
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import (
    JGRANTS_API_BASE,
    REQUEST_TIMEOUT,
    ROBOTS_LOG,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

# 自動アクセスするURLのみチェック対象にする
TARGET_URLS = [f"{JGRANTS_API_BASE}/subsidies"]


def _fetch_robots_txt(host: str) -> tuple[str | None, str]:
    """robots.txt の本文と備考を返す。404は「制限なし」として空Allowを返す。"""
    url = f"https://{host}/robots.txt"
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        return None, f"取得失敗: {type(exc).__name__}"

    if response.status_code == 404:
        return "", "robots.txt 不存在 → 制限なしと解釈 (RFC 9309)"
    if response.status_code >= 400:
        return None, f"取得失敗: HTTP {response.status_code}"
    return response.text, f"取得成功: HTTP {response.status_code}"


def check_robots() -> bool:
    """自動アクセス対象URLについて robots.txt の can_fetch を確認。"""
    all_ok = True
    notes = []
    checked_hosts: dict[str, str] = {}

    for target_url in TARGET_URLS:
        host = urlparse(target_url).hostname or ""
        if host not in checked_hosts:
            content, source_note = _fetch_robots_txt(host)
            checked_hosts[host] = source_note
            notes.append(f"- host `{host}`: {source_note}")
            if content is None:
                # 取得失敗は fail-close
                all_ok = False
                continue

            rp = RobotFileParser()
            rp.parse(content.splitlines())
            # 空の robots.txt は全許可 (parse後 can_fetch は True を返す)
        else:
            content = ""  # 既に確認済みでもチェック自体は実施
            rp = RobotFileParser()
            # 同じhostの2回目以降は最初の結果を信用するが、PoCでは単純化のため再パース
            content, _ = _fetch_robots_txt(host)
            rp.parse((content or "").splitlines())

        ok = rp.can_fetch(USER_AGENT, target_url)
        notes.append(f"  - `{target_url}` → {'OK' if ok else 'DISALLOW'}")
        if not ok:
            all_ok = False

    summary = "OK" if all_ok else "DISALLOW検出"
    _append_log("(hostごとに取得)", all_ok, summary, notes)
    return all_ok


def _append_log(robots_url: str, ok: bool, summary: str, notes: list[str] | None = None) -> None:
    ROBOTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    block = [
        f"## {timestamp}",
        f"- robots.txt: `{robots_url}`",
        f"- 判定: **{summary}**",
        f"- User-Agent: `{USER_AGENT}`",
    ]
    if notes:
        block.extend(notes)
    block.append("")
    header_needed = not ROBOTS_LOG.exists()
    with ROBOTS_LOG.open("a", encoding="utf-8") as f:
        if header_needed:
            f.write("# robots.txt 確認ログ\n\n")
        f.write("\n".join(block) + "\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ok = check_robots()
    if not ok:
        logger.error("robots.txtでDisallowが検出されました。スクレイピングを中止してください。")
        return 1
    logger.info("robots.txtチェックOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
