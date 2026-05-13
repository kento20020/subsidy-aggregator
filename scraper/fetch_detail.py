"""新着・更新分の補助金について jGrants 詳細API を叩いて本文を取得する。

- 対象: subsidies の `tag_status == "pending"` （diff_check が新規/更新と判定したもの）
- 出力: 各レコードに body_text, body_html, catch_phrase, use_purpose_text,
  subsidy_rate, industry_raw, project_end_deadline, front_url を追加
- ポライトネス: 1リクエストごとに0.5秒sleep
- 詳細APIが失敗した場合は body_text="" のままにし、tag_statusは維持（AI側で扱う）
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone

from .config import DATA_FILE, JGRANTS_API_BASE
from .http_client import get_safe
from .sanitize import clean_text

logger = logging.getLogger(__name__)

DETAIL_SLEEP_SEC = 0.5
DETAIL_MAX_BODY_CHARS = 5000  # AI入力前のtruncate上限。sanitize.cleanで3000まで再縮小される


def _extract_api_id(record: dict) -> str | None:
    """`url` フィールド末尾から salesforce ID を抽出。"""
    url = record.get("url", "")
    if "/subsidy/" not in url:
        return None
    return url.rsplit("/", 1)[-1] or None


def _fetch_one(api_id: str) -> dict | None:
    """詳細APIを叩いて先頭resultを返す。失敗時None。"""
    endpoint = f"{JGRANTS_API_BASE}/subsidies/id/{api_id}"
    try:
        response = get_safe(endpoint)
    except Exception as exc:
        logger.warning("詳細API失敗 id=%s: %s", api_id, type(exc).__name__)
        return None
    if response.status_code != 200:
        logger.warning("詳細API non-200 id=%s status=%d", api_id, response.status_code)
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    results = payload.get("result", [])
    return results[0] if results else None


def _merge_detail(record: dict, detail: dict) -> dict:
    """詳細APIのフィールドを既存recordに統合。"""
    body_html = detail.get("detail") or ""
    body_text = clean_text(body_html, max_chars=DETAIL_MAX_BODY_CHARS)

    project_end = detail.get("project_end_deadline")
    if project_end:
        project_end = project_end[:10]

    return {
        **record,
        "body": body_text,  # 既存bodyを置き換え（titleの繰り返しから本文へ）
        "body_html_len": len(body_html),
        "catch_phrase": clean_text(detail.get("subsidy_catch_phrase", ""), max_chars=200),
        "use_purpose_text": clean_text(detail.get("use_purpose", ""), max_chars=100),
        "industry_raw": clean_text(detail.get("industry", ""), max_chars=500),
        "subsidy_rate_official": clean_text(detail.get("subsidy_rate", ""), max_chars=50),
        "project_end_deadline": project_end,
        "front_url": detail.get("front_subsidy_detail_page_url") or record.get("url"),
        "detail_fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def run() -> dict:
    if not DATA_FILE.exists():
        logger.error("data/subsidies.json が存在しません。")
        return {"fetched": 0, "skipped": 0, "failed": 0}

    state = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    subsidies = state.get("subsidies", [])

    fetched = skipped = failed = 0
    for i, record in enumerate(subsidies):
        if record.get("tag_status") != "pending":
            skipped += 1
            continue
        api_id = _extract_api_id(record)
        if not api_id:
            logger.warning("api_id 抽出失敗: id=%s", record.get("id"))
            failed += 1
            continue

        detail = _fetch_one(api_id)
        if detail is None:
            failed += 1
            continue

        subsidies[i] = _merge_detail(record, detail)
        fetched += 1
        if fetched % 10 == 0:
            logger.info("fetch_detail 進捗: %d件取得済", fetched)
        time.sleep(DETAIL_SLEEP_SEC)

    state["subsidies"] = subsidies
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    DATA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("詳細取得: 完了=%d スキップ=%d 失敗=%d", fetched, skipped, failed)
    return {"fetched": fetched, "skipped": skipped, "failed": failed}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
