"""新着/更新分の補助金本文からAIが「読まなくて済む情報」を構造化抽出する。

PoC Phase 1.6 改訂:
- summary中心 → 抽出中心へ。
- 入力: fetch_detail.py が取得した body + 構造化フィールド
- 出力スキーマ:
  - concrete_targets: 具体的対象 (3-5件)
  - eligible_expenses: 対象経費 (3-7件)
  - required_documents: 主な必要書類 (2-5件)
  - key_warnings: 注意点・除外条件 (該当者がスキップ判定に使う)
  - plain_summary: 平易日本語1-2文の要約
  - difficulty: 申請難易度 1-5
  - industry_tags / size_tags / purpose_tags: フィルタ用 (UI互換)

モック分岐: API キー未設定 or --dry-run。本文 + 構造化フィールドからヒューリスティック抽出。
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
AI_MAX_BODY_CHARS = 3000  # Haikuに渡す本文の上限

INDUSTRY_KEYWORDS = {
    "IT": ["IT", "DX", "デジタル", "クラウド", "SaaS", "AI", "情報通信"],
    "製造業": ["製造", "ものづくり", "工場", "機械"],
    "飲食": ["飲食", "外食", "レストラン", "食堂"],
    "農業": ["農業", "農家", "農産", "漁業"],
    "建設": ["建設", "建築", "土木"],
    "小売": ["小売", "店舗", "EC", "商業"],
    "医療": ["医療", "病院", "介護"],
    "教育": ["教育", "学校", "学習"],
}
# universal フラグ判定用 (本文に「業種不問」相当の明示があるか)
UNIVERSAL_INDUSTRY_KEYWORDS = ["業種不問", "業種を問わず", "業種制限なし", "全業種対象", "すべての業種", "あらゆる業種"]
# 9カテゴリ外の業種を「その他」に振り分けるためのキーワード
OTHER_INDUSTRY_KEYWORDS = ["金融", "保険", "不動産", "運輸", "物流", "観光", "宿泊", "エネルギー", "電気・ガス"]
PURPOSE_KEYWORDS = {
    "設備投資": ["設備", "機械", "装置", "投資"],
    "IT導入": ["IT導入", "システム", "DX", "デジタル"],
    "人材育成": ["人材", "研修", "育成", "雇用"],
    "販路開拓": ["販路", "海外展開", "輸出", "マーケ"],
    "研究開発": ["研究", "開発", "R&D", "技術"],
    "省エネ": ["省エネ", "脱炭素", "カーボン", "GX"],
    "海外展開": ["海外", "輸出", "海外展開"],
}
SIZE_KEYWORDS = {
    "個人事業主": ["個人事業"],
    "小規模事業者": ["小規模"],
    "中小企業": ["中小企業"],
    "大企業": ["大企業"],
}

SYSTEM_PROMPT = """あなたは日本の補助金情報の要点を抽出するアシスタントです。
本文を読み、申請を検討する事業者が3秒で判断するために必要な情報だけを抽出してください。
回答は厳格なJSONのみ。余分なテキスト・マークダウン・バックティック・コードブロック禁止。

スキーマ:
{
  "concrete_targets": ["対象者の具体像を3-5件、本文の語をそのまま使う"],
  "eligible_expenses": ["補助対象となる経費を3-7件"],
  "required_documents": ["申請時に提出が必要な主な書類を2-5件"],
  "key_warnings": ["対象外となる事業者・地域・条件を1-3件。該当者がスキップ判断できる粒度で"],
  "plain_summary": "平易な日本語で1-2文。役所表現は具体例に置き換える。100字以内。",
  "difficulty": 1,
  "industry_tags": ["IT","製造業","飲食","農業","建設","小売","医療","教育","その他" のうち該当0-3個],
  "industry_universal": false,
  "industry_inferred": false,
  "size_tags": ["個人事業主/小規模事業者/中小企業/大企業/全規模 から該当を選ぶ"],
  "purpose_tags": ["設備投資/IT導入/人材育成/販路開拓/研究開発/省エネ/海外展開 から該当を選ぶ"]
}

difficulty: 1=申請書1枚程度の簡易, 3=事業計画書必要, 5=採択率低く詳細書類多数

industry に関する重要ルール:
1. 9カテゴリは「IT/製造業/飲食/農業/建設/小売/医療/教育/その他」のみ。「全業種」はタグ値ではない
2. 本文に「業種不問」「全業種対象」「業種を問わず」など明示 → industry_universal=true, industry_tags=[] (必ず空配列。併存禁止)
3. 本文に業種が明示されている → industry_tags にマップ、industry_universal=false, industry_inferred=false
4. 本文に業種記述なし、AIが文脈から推測 → industry_inferred=true (tagsは推測結果か空)
5. 9カテゴリのどれにも該当しない業種 (金融/不動産/運輸/観光等) → industry_tags=["その他"]
"""


def _heuristic_extract(record: dict) -> dict:
    """モック分岐用の決定論的抽出。body+構造化フィールドからキーワード走査。"""
    body = record.get("body", "") or ""
    title = record.get("title", "") or ""
    industry_raw = record.get("industry_raw", "") or ""
    text = " ".join([title, body, industry_raw, record.get("use_purpose_text", "")])

    # === industry: 3-field (Phase 1, TECH_DEF §1.1) ===
    industry_universal = any(kw in text for kw in UNIVERSAL_INDUSTRY_KEYWORDS)
    if industry_universal:
        # universal=true なら tags=[] (併存禁止、TECH_DEF ルール 5)
        industries = []
        industry_inferred = False
    else:
        industries = [k for k, ws in INDUSTRY_KEYWORDS.items() if any(w in text for w in ws)]
        if not industries:
            # 9カテゴリ外の業種が明示されているかチェック
            if any(kw in text for kw in OTHER_INDUSTRY_KEYWORDS):
                industries = ["その他"]
                industry_inferred = False
            else:
                # 業種記述なし、推測も困難 → 空 + inferred=true
                industries = []
                industry_inferred = True
        else:
            # 上限 3 個 (TECH_DEF サニタイズで切る前にここで先取り)
            industries = industries[:3]
            industry_inferred = False
    # === size/purpose: Phase 2/3 で更新予定、Phase 1 では旧ロジック維持 ===
    purposes = [k for k, ws in PURPOSE_KEYWORDS.items() if any(w in text for w in ws)]
    sizes = [k for k, ws in SIZE_KEYWORDS.items() if any(w in text for w in ws)]
    if not sizes:
        sizes = ["中小企業"]
    if not purposes:
        purposes = ["設備投資"]

    # concrete_targets: 本文中の対象者表現を粗抽出
    concrete = []
    for marker in ["中小企業", "小規模事業者", "個人事業主", "創業", "スタートアップ"]:
        if marker in text and marker not in concrete:
            concrete.append(marker)
    if record.get("target_text"):
        concrete.append(record["target_text"])
    if not concrete:
        concrete = ["中小企業者"]

    # eligible_expenses: 本文中の「経費」「費」を含む短い項目を抽出
    expenses = []
    for keyword in ["設備", "システム導入", "外注費", "人件費", "研修", "広告宣伝", "出願手数料", "翻訳費", "代理人費用"]:
        if keyword in text:
            expenses.append(keyword)
    if not expenses:
        expenses = ["対象経費(本文参照)"]
    expenses = expenses[:7]

    # required_documents: 一般的なテンプレ
    docs = []
    for d in ["事業計画書", "決算書", "見積書", "履歴事項全部証明書", "申請書"]:
        if d in text:
            docs.append(d)
    if not docs:
        docs = ["申請書", "事業計画書"]

    # warnings: 地域限定や対象外を検出
    warnings = []
    pref = record.get("prefecture", "")
    if pref and pref not in ("全国", "全都道府県", ""):
        warnings.append(f"{pref}内の事業者限定")
    if "個人事業主は対象外" in text or ("法人" in text and "個人事業主" not in text and "個人" not in text):
        # 弱いシグナル
        pass
    if "創業" in text and "年以内" in text:
        warnings.append("創業からの経過年数に条件あり (本文参照)")

    # plain_summary: catch_phraseがあれば優先、なければ短いtitle+amount
    cp = record.get("catch_phrase", "")
    purpose = record.get("use_purpose_text", "")
    amount = record.get("amount_text", "")
    parts = [p for p in [cp, purpose] if p]
    if parts:
        plain = "・".join(parts)
        if amount:
            plain += f"。{amount}まで。"
    else:
        plain = title[:80]
    plain = plain[:100]

    # difficulty: 補助額に応じた粗推定（PoCモック）
    amount_max = record.get("subsidy_max_limit") or 0
    if not amount_max:
        m = re.search(r"([\d,]+)円", amount)
        if m:
            try:
                amount_max = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    if amount_max >= 50_000_000:
        difficulty = 5
    elif amount_max >= 10_000_000:
        difficulty = 4
    elif amount_max >= 3_000_000:
        difficulty = 3
    elif amount_max >= 500_000:
        difficulty = 2
    else:
        difficulty = 1

    # amount_max (万円換算) for sort
    amount_max_man = (amount_max // 10000) if amount_max else 0

    return {
        "concrete_targets": concrete[:5],
        "eligible_expenses": expenses,
        "required_documents": docs[:5],
        "key_warnings": warnings[:3],
        "plain_summary": plain,
        "difficulty": difficulty,
        "industry_tags": industries,
        "industry_universal": industry_universal,
        "industry_inferred": industry_inferred,
        "size_tags": sizes,
        "purpose_tags": purposes,
        "amount_max": amount_max_man,
    }


def _call_anthropic(record: dict) -> dict | None:
    """Anthropic API 呼び出し。失敗時None。"""
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.error("anthropic パッケージが未インストール")
        return None

    body = clean_text(record.get("body", ""), max_chars=AI_MAX_BODY_CHARS)
    user_prompt = (
        f"# 補助金タイトル\n{record.get('title', '')}\n\n"
        f"# キャッチフレーズ\n{record.get('catch_phrase', '')}\n\n"
        f"# 用途\n{record.get('use_purpose_text', '')}\n\n"
        f"# 対象業種\n{record.get('industry_raw', '')[:500]}\n\n"
        f"# 補助率\n{record.get('subsidy_rate_official', '')}\n\n"
        f"# 補助上限\n{record.get('amount_text', '')}\n\n"
        f"# 対象規模\n{record.get('target_text', '')}\n\n"
        f"# 締切\n{record.get('deadline', '')}\n\n"
        f"# 本文\n{body}\n"
    )
    try:
        client = Anthropic()
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text.strip()
        # コードブロックで囲まれた場合の除去
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception as exc:
        logger.warning("Anthropic API失敗: %s", type(exc).__name__)
        return None


ALLOWED_KEYS = {
    "concrete_targets", "eligible_expenses", "required_documents",
    "key_warnings", "plain_summary", "difficulty",
    "industry_tags", "size_tags", "purpose_tags",
    # Phase 1 (TECH_DEF §1.1) で追加
    "industry_universal", "industry_inferred",
}

# 9 カテゴリ allowlist (TECH_DEF §1.1)。「全業種」はタグ値ではない (universal で表現)
INDUSTRY_ALLOWLIST = {"IT", "製造業", "飲食", "農業", "建設", "小売", "医療", "教育", "その他"}


def _apply_result(record: dict, result: dict) -> None:
    """AI/モック結果を record にマージ。型をある程度サニタイズ。"""
    for k in ALLOWED_KEYS:
        if k not in result:
            continue
        v = result[k]
        if k in {"concrete_targets", "eligible_expenses", "required_documents",
                 "key_warnings", "size_tags", "purpose_tags"}:
            if isinstance(v, list):
                record[k] = [clean_text(str(x), max_chars=80) for x in v if x]
        elif k == "industry_tags":
            # Phase 1: allowlist で filter、最大 3 個
            if isinstance(v, list):
                cleaned = [clean_text(str(x), max_chars=80) for x in v if x]
                record[k] = [t for t in cleaned if t in INDUSTRY_ALLOWLIST][:3]
        elif k in {"industry_universal", "industry_inferred"}:
            record[k] = bool(v)
        elif k == "plain_summary":
            record[k] = clean_text(str(v), max_chars=140)
        elif k == "difficulty":
            try:
                record[k] = max(1, min(5, int(v)))
            except (TypeError, ValueError):
                pass
    # Phase 1: universal=true なら tags=[] (TECH_DEF ルール 5、AI が誤って併存させても補正)
    if record.get("industry_universal") is True:
        record["industry_tags"] = []
    # amount_max for sort (heuristicから or APIから)
    if "amount_max" in result:
        try:
            record["amount_max"] = int(result["amount_max"])
        except (TypeError, ValueError):
            pass


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
        status = record.get("tag_status")
        if status == "done":
            skipped += 1
            continue
        if status == "mocked" and use_mock:
            skipped += 1
            continue

        if use_mock:
            result = _heuristic_extract(record)
            _apply_result(record, result)
            record["tag_status"] = "mocked"
            tagged += 1
        else:
            result = _call_anthropic(record)
            if result is None:
                record["tag_status"] = "failed"
                failed += 1
                continue
            _apply_result(record, result)
            # amount_max は heuristicの推定値でも埋める (本番AIは数値を返さないため)
            if not record.get("amount_max"):
                heuristic = _heuristic_extract(record)
                record["amount_max"] = heuristic.get("amount_max", 0)
            record["tag_status"] = "done"
            tagged += 1

    state["subsidies"] = subsidies
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    DATA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("AI抽出: 完了=%d スキップ=%d 失敗=%d", tagged, skipped, failed)
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
