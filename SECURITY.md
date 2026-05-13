# セキュリティチェックリスト

PoC のセキュリティ対策一覧。コードレビューまたはデプロイ前に上から確認する。

## 機密情報

- [ ] APIキーは `.env` か GitHub Secrets のみで管理（コード直書き禁止）
- [ ] `.gitignore` に `.env` `*.key` `.secrets/` が含まれる
- [ ] ログにAPIキー・本文・レスポンス全文を出していない
- [ ] `grep -rni "sk-ant" scraper/ templates/` が 0件

## ネットワーク (SSRF/タイムアウト)

- [ ] 全 httpx 呼び出しに `timeout=30` 設定
- [ ] `scraper/http_client.py` で `ALLOWED_HOSTS` 検証を通ったURLのみアクセス
- [ ] リダイレクトは手動追従・最大3回・allowlist内のみ
- [ ] IPv4/IPv6 リテラルURLは拒否
- [ ] 取得件数は50件上限・本文は3000字 truncate

## robots.txt

- [ ] `python -m scraper.robots_check` が起動時に `can_fetch` を確認
- [ ] 確認結果が `docs/robots_check.md` に記録される
- [ ] Disallow違反検出時は例外で停止する

## XSS / テンプレート

- [ ] Jinja2 Environment は `autoescape=select_autoescape(["html", "xml"])`
- [ ] `grep -rn "|safe" templates/` が 0件
- [ ] `base.html.j2` に CSP メタタグ（`default-src 'self'` 系）あり
- [ ] AI生成テキスト（summary・tags）もエスケープ経由で出力
- [ ] 外部CDN・外部フォントを使わない（CSPで弾く）

## CI / 権限

- [ ] `.github/workflows/update.yml` の `permissions` が `contents: write` のみ
- [ ] `ANTHROPIC_API_KEY` は `${{ secrets.* }}` 経由のみ
- [ ] ワークフロー内で `echo $ANTHROPIC_API_KEY` のような露出をしていない

## 依存関係

- [ ] `requirements.txt` のバージョンが `==` で固定
- [ ] 月1回 `pip-audit` を実行する運用にする（手動でOK）
