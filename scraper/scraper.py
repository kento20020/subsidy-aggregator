"""jGrants 公開APIから公募中の補助金一覧を取得して data/subsidies.json に書き出す。

note: 詳細本文の取得APIは将来対応（TODO）。現状はタイトル＋target_area＋target_employees の連結を本文代わりに使う。
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone

from .config import (
    DATA_FILE,
    JGRANTS_API_BASE,
    JGRANTS_SITE_BASE,
    MAX_RECORDS,
)
from .http_client import get_safe
from .robots_check import check_robots
from .sanitize import clean_text

logger = logging.getLogger(__name__)


def fetch_jgrants() -> list[dict]:
    """jGrants 公募中一覧を取得して正規化済みのレコード配列を返す。"""
    endpoint = f"{JGRANTS_API_BASE}/subsidies"
    params = {
        "keyword": "補助金",  # 必須パラメータ。広めに引っ掛けるため一般語
        "sort": "created_date",
        "order": "DESC",
        "acceptance": "1",  # 公募中のみ
    }
    response = get_safe(endpoint, params=params)
    if response.status_code != 200:
        logger.error("jGrants API error: status=%d", response.status_code)
        return []

    payload = response.json()
    raw_records = payload.get("result", [])[:MAX_RECORDS]
    logger.info("jGrants API: %d件取得", len(raw_records))

    fetched_at = datetime.now(timezone.utc).isoformat()
    records = []
    for raw in raw_records:
        record = _normalize(raw, fetched_at)
        if record:
            records.append(record)
    return records


def _normalize(raw: dict, fetched_at: str) -> dict | None:
    api_id = raw.get("id")
    name = raw.get("name") or api_id
    title = clean_text(raw.get("title"))
    if not api_id or not title:
        return None

    deadline = raw.get("acceptance_end_datetime")
    if deadline:
        deadline = deadline[:10]

    subsidy_max = raw.get("subsidy_max_limit")
    amount_text = f"最大{int(subsidy_max):,}円" if isinstance(subsidy_max, (int, float)) else ""

    target_text = clean_text(raw.get("target_number_of_employees"))
    target_area = clean_text(raw.get("target_area_search"))

    body_parts = [p for p in [title, target_area, target_text] if p]
    body = clean_text(" / ".join(body_parts))

    hash_src = f"{title}|{deadline or ''}|{amount_text}|{target_text}"
    content_hash = hashlib.sha256(hash_src.encode("utf-8")).hexdigest()

    return {
        "id": f"jgrants-{name}",
        "title": title,
        "url": f"{JGRANTS_SITE_BASE}/subsidy/{api_id}",
        "source": "jGrants",
        "body": body,
        "deadline": deadline,
        "amount_text": amount_text,
        "target_text": target_text,
        "prefecture": target_area,
        "fetched_at": fetched_at,
        "content_hash": content_hash,
    }


def save(records: list[dict]) -> None:
    """取得した生レコードを subsidies.json の "raw" 部分に書き出す。
    diff_check が既存の subsidies と合わせて追記マージする。"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        existing = {"updated_at": None, "total": 0, "subsidies": []}
    existing["fetched_raw"] = records
    existing["fetched_at"] = datetime.now(timezone.utc).isoformat()
    DATA_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not check_robots():
        logger.error("robots.txtチェックに失敗したため中止します。")
        return 1
    records = fetch_jgrants()
    save(records)
    logger.info("data/subsidies.json に %d件のraw記録を保存", len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
