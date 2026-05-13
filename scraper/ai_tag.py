"""Claude Haiku で新着/更新分のタグ付け・要約を行う。

- ANTHROPIC_API_KEY 未設定 or --dry-run でモック分岐。
- モックはタイトルからヒューリスティックに決定論的タグを返す（オフライン動作確認用）。
- 本番呼び出し失敗時は tag_status="failed" で続行（後続実行で再試行されない点に注意。
  PoCではpendingのままにせず、failureを残して手動確認を促す方針）。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from .config import DATA_FILE
from .sanitize import clean_text

logger = logging.getLogger(__name__)

MODEL_ID = "claude-haiku-4-5"

INDUSTRY_KEYWORDS = {
    "IT": ["IT", "DX", "デジタル", "クラウド", "SaaS", "AI"],
    "製造業": ["製造", "ものづくり", "工場"],
    "飲食": ["飲食", "外食", "レストラン", "食堂"],
    "農業": ["農業", "農家", "農産"],
    "建設": ["建設", "建築", "土木"],
    "小売": ["小売", "店舗", "EC"],
    "医療": ["医療", "病院", "介護"],
    "教育": ["教育", "学校", "学習"],
}
PURPOSE_KEYWORDS = {
    "設備投資": ["設備", "機械", "装置"],
    "IT導入": ["IT導入", "システム", "DX", "デジタル"],
    "人材育成": ["人材", "研修", "育成", "雇用"],
    "販路開拓": ["販路", "海外展開", "輸出", "マーケ"],
    "研究開発": ["研究", "開発", "R&D", "技術"],
    "省エネ": ["省エネ", "脱炭素", "カーボン", "GX"],
    "海外展開": ["海外", "輸出"],
}
SIZE_KEYWORDS = {
    "個人事業主": ["個人事業"],
    "小規模事業者": ["小規模"],
    "中小企業": ["中小企業"],
    "大企業": ["大企業"],
}

SYSTEM_PROMPT = """あなたは日本の補助金情報を分類するアシスタントです。
以下のJSONのみを返してください。余分なテキスト・マークダウン・バックティック不要。

{
  "industry_tags": [],
  "size_tags": [],
  "purpose_tags": [],
  "amount_min": 0,
  "amount_max": 0,
  "subsidy_rate": "",
  "urgency": 1,
  "summary": ""
}

選択肢:
- industry_tags: IT, 製造業, 飲食, 農業, 建設, 小売, 医療, 教育, 全業種
- size_tags: 個人事業主, 小規模事業者, 中小企業, 大企業, 全規模
- purpose_tags: 設備投資, IT導入, 人材育成, 販路開拓, 研究開発, 省エネ, 海外展開
- urgency: 1(余裕あり)〜5(7日以内)
- subsidy_rate: 例 "1/2" "2/3" "定額" "不明"
"""


def _heuristic_tags(record: dict) -> dict:
    """モック分岐用の決定論的タグ付け。"""
    text = " ".join([record.get("title", ""), record.get("body", "")])
    industry = [k for k, ws in INDUSTRY_KEYWORDS.items() if any(w in text for w in ws)]
    purpose = [k for k, ws in PURPOSE_KEYWORDS.items() if any(w in text for w in ws)]
    size = [k for k, ws in SIZE_KEYWORDS.items() if any(w in text for w in ws)]

    if not industry:
        industry = ["全業種"]
    if not size:
        size = ["中小企業"]
    if not purpose:
        purpose = ["設備投資"]

    amount_text = record.get("amount_text", "")
    m = re.search(r"([\d,]+)", amount_text)
    amount_max = int(m.group(1).replace(",", "")) // 10000 if m else 0  # 万円換算

    summary = clean_text(record.get("title", ""), max_chars=120)
    if record.get("deadline"):
        summary = f"{summary}（締切 {record['deadline']}）"

    return {
        "industry_tags": industry,
        "size_tags": size,
        "purpose_tags": purpose,
        "amount_min": 0,
        "amount_max": amount_max,
        "subsidy_rate": "不明",
        "summary": summary,
    }


def _call_anthropic(record: dict) -> dict | None:
    """本番API呼び出し。失敗時はNone。"""
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.error("anthropic パッケージが未インストール")
        return None

    client = Anthropic()
    user_prompt = (
        f"タイトル: {record.get('title', '')}\n"
        f"本文: {record.get('body', '')}\n"
        f"締切: {record.get('deadline', '不明')}\n"
        f"補助額: {record.get('amount_text', '不明')}\n"
        f"対象: {record.get('target_text', '不明')}\n"
    )
    try:
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text.strip()
        return json.loads(text)
    except Exception as exc:
        logger.warning("Anthropic API失敗: %s", type(exc).__name__)
        return None


def run(dry_run: bool = False) -> dict:
    if not DATA_FILE.exists():
        logger.error("data/subsidies.json が存在しません。")
        return {"tagged": 0, "skipped": 0, "failed": 0}

    state = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    subsidies = state.get("subsidies", [])

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    use_mock = dry_run or not has_key
    if use_mock:
        logger.info("モックモードで動作（dry_run=%s, has_key=%s）", dry_run, has_key)

    tagged = skipped = failed = 0
    for record in subsidies:
        if record.get("tag_status") not in ("pending", "failed"):
            skipped += 1
            continue

        if use_mock:
            tags = _heuristic_tags(record)
            record.update(tags)
            record["tag_status"] = "mocked"
            tagged += 1
        else:
            result = _call_anthropic(record)
            if result is None:
                record["tag_status"] = "failed"
                failed += 1
                continue
            allowed_keys = {
                "industry_tags", "size_tags", "purpose_tags",
                "amount_min", "amount_max", "subsidy_rate",
                "urgency", "summary",
            }
            for k in allowed_keys:
                if k in result:
                    record[k] = result[k]
            record["tag_status"] = "done"
            tagged += 1

    state["subsidies"] = subsidies
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    DATA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("AIタグ付け: 完了=%d スキップ=%d 失敗=%d", tagged, skipped, failed)
    return {"tagged": tagged, "skipped": skipped, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="API呼ばずモックで動作")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
