"""scraper.py が書いた fetched_raw を既存の subsidies と突合し、
新規/更新/維持を判定して subsidies フィールドを再構築する。

- 新規: 既存にidが無い → is_new=True, first_seen_at=fetched_at, tag_status="pending"
- 更新: 既存ありで content_hash が変わった → updated_at=fetched_at, tag_status="pending"
- 維持: 既存ありで hash 同じ → 既存タグをそのまま使う
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from .config import DATA_FILE

logger = logging.getLogger(__name__)


def run() -> dict:
    if not DATA_FILE.exists():
        logger.error("data/subsidies.json が存在しません。先に scraper.scraper を実行してください。")
        return {"new": 0, "updated": 0, "kept": 0, "removed": 0}

    state = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    raw = state.get("fetched_raw", [])
    existing = {s["id"]: s for s in state.get("subsidies", [])}

    now = datetime.now(timezone.utc).isoformat()
    new_count = updated_count = kept_count = 0
    out = []
    seen_ids = set()

    for r in raw:
        seen_ids.add(r["id"])
        prev = existing.get(r["id"])
        if prev is None:
            record = {
                **r,
                "first_seen_at": r["fetched_at"],
                "updated_at": r["fetched_at"],
                "is_new": True,
                "tag_status": "pending",
                # フィルタ用タグ（AIがbody由来で埋める）
                "industry_tags": [],
                "size_tags": [],
                "purpose_tags": [],
                # AI抽出スキーマ（fetch_detail + ai_tag で埋まる）
                "concrete_targets": [],
                "eligible_expenses": [],
                "required_documents": [],
                "key_warnings": [],
                "plain_summary": "",
                "difficulty": 0,
                # 派生フィールド
                "urgency": _calc_urgency(r.get("deadline")),
                "amount_max": 0,
            }
            new_count += 1
        elif prev.get("content_hash") != r["content_hash"]:
            record = {
                **prev,
                **r,
                "first_seen_at": prev.get("first_seen_at", r["fetched_at"]),
                "updated_at": now,
                "is_new": _is_recently_new(prev.get("first_seen_at")),
                "tag_status": "pending",
                "urgency": _calc_urgency(r.get("deadline")),
            }
            updated_count += 1
        else:
            # 維持: content_hash 不変。AI結果(prev)は保持しつつ raw 由来の新フィールド(prefecture等)を追従。
            record = {
                **r,
                **prev,
                "fetched_at": r["fetched_at"],
                "is_new": _is_recently_new(prev.get("first_seen_at")),
                "urgency": _calc_urgency(r.get("deadline")),
            }
            kept_count += 1
        out.append(record)

    removed_count = len(existing) - len(seen_ids & set(existing.keys()))
    state["subsidies"] = out
    state["total"] = len(out)
    state["updated_at"] = now
    state.pop("fetched_raw", None)
    DATA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "diff: 新規=%d 更新=%d 維持=%d 削除(対象外)=%d",
        new_count, updated_count, kept_count, removed_count,
    )
    return {
        "new": new_count,
        "updated": updated_count,
        "kept": kept_count,
        "removed": removed_count,
    }


def _calc_urgency(deadline: str | None) -> int:
    if not deadline:
        return 1
    try:
        d = datetime.fromisoformat(deadline).replace(tzinfo=timezone.utc)
    except ValueError:
        return 1
    now = datetime.now(timezone.utc)
    diff = (d - now).days
    if diff < 0:
        return 1
    if diff <= 7:
        return 5
    if diff <= 14:
        return 4
    if diff <= 30:
        return 3
    if diff <= 90:
        return 2
    return 1


def _is_recently_new(first_seen_at: str | None) -> bool:
    if not first_seen_at:
        return False
    try:
        d = datetime.fromisoformat(first_seen_at)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - d).days <= 7


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
