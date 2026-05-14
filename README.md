# 補助金まとめ

公募中の日本の補助金を、AI が「読まなくても3秒で判断できる形」に整理した静的サイト。
広告なし・会員登録不要・オープンソース。毎朝 8:00 JST に自動更新。

🌐 公開サイト: https://kento20020.github.io/subsidy-aggregator/

## このサイトの特徴

- **広告なし・会員登録不要** — トラッキング目的の Cookie も使いません
- **AIが要点を整理** — 「対象者・対象経費・必要書類・注意点」を本文から構造化抽出
- **毎朝自動更新** — GitHub Actions が新着・更新を検知
- **既読は自動でグレーアウト** — 新着・更新だけが目立つ
- **質問形式の絞り込みウィザード** — 初回訪問時に4問で条件設定
- **オープンソース** — コード・データ取得元すべて公開

## データソース

[Jグランツ（デジタル庁）](https://www.jgrants-portal.go.jp) の[公開API](https://www.jgrants-portal.go.jp/open-api) を利用しています。
政府標準利用規約 2.0 に準拠し、出典を明記。

---

## 開発者向け: ローカルセットアップ

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 実行（プロジェクトルートから）

```powershell
# 1. robots.txt チェック (jGrants 側のクローラ制限を確認)
python -m scraper.robots_check

# 2. 一覧APIから補助金リストを取得
python -m scraper.scraper

# 3. 前回データと差分検出 (SHA256ハッシュ)
python -m scraper.diff_check

# 4. 新着・更新分の本文を詳細APIで取得
python -m scraper.fetch_detail

# 5. AI 構造化抽出 (ANTHROPIC_API_KEY 未設定なら自動モック)
python -m scraper.ai_tag           # 本番 (Claude Haiku 呼び出し)
python -m scraper.ai_tag --dry-run # 強制モック

# 6. 静的サイト生成 (docs/ に index/detail/404/sitemap/robots.txt)
python -m scraper.build

# 7. ローカルプレビュー
python -m http.server 8000 --bind 127.0.0.1 --directory docs
# → http://127.0.0.1:8000
```

## 環境変数

`.env` ファイルかシェルで設定 (コードリテラル禁止):

| 変数 | 説明 | 必須 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー | 任意 (未設定時はモック動作) |

## 自動更新 (GitHub Actions)

`.github/workflows/update.yml` が毎日 23:00 UTC (= 8:00 JST) に走り、
取得 → 差分 → 詳細 → AI抽出 → ビルド → commit & push を実行します。

リポジトリ側で必要な設定:
- Secret: `ANTHROPIC_API_KEY`
- Settings → Pages → Source: `Deploy from a branch`, Branch: `main`, Folder: `/docs`

## ディレクトリ構成

```
alartAPP/
├── scraper/        # 取得・差分・AI抽出・ビルドの各スクリプト
├── templates/      # Jinja2 テンプレ (XSS対策で autoescape ON, |safe 禁止)
├── data/           # subsidies.json (差分検出用の状態保存)
├── docs/           # GitHub Pages 公開ディレクトリ (生成物)
├── worker/         # Cloudflare Worker (自然文 → フィルタ値の解釈)
├── tools/          # OGP画像生成など補助ツール
├── .github/        # GitHub Actions ワークフロー
├── SECURITY.md     # セキュリティチェックリスト
└── README.md
```

## セキュリティ

`SECURITY.md` 参照。主要な防御:
- SSRF: HTTP通信はホストallowlist + IPリテラル拒否 + 手動リダイレクト
- XSS: Jinja2 autoescape ON, `|safe` 禁止, JSON-LD は `|tojson` 経由
- CSP: `default-src 'self'`, インラインスクリプト不可
- APIキー: コード直書き禁止 (`.env` / GitHub Secrets / wrangler secret のみ)
- DoS/コスト対策: 取得件数50件上限, 本文3000字 truncate

## ライセンス

MIT (予定)。データは Jグランツ公開API由来で、政府標準利用規約 2.0 に準拠して再配布しています。
