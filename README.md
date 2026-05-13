# 補助金まとめサイト PoC

jGrants の公募中補助金情報を毎日自動収集して静的サイトとして公開する PoC。

## セットアップ

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 実行

すべてプロジェクトルートから実行する。

```powershell
# 1. robots.txt チェック
python -m scraper.robots_check

# 2. スクレイピング（jGrants公開APIを叩く）
python -m scraper.scraper

# 3. 差分検出
python -m scraper.diff_check

# 4. AIタグ付け（ANTHROPIC_API_KEY未設定なら自動モック）
python -m scraper.ai_tag           # 本番
python -m scraper.ai_tag --dry-run # 強制モック

# 5. 静的サイト生成
python -m scraper.build

# 6. ローカルプレビュー
python -m http.server 8000 --directory docs
# → http://localhost:8000
```

## 環境変数

`.env` ファイルかシェルで設定（コードに直書き禁止）:

| 変数 | 説明 | 必須 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー | 任意（未設定時はモック動作） |

## 構成

- `scraper/` — 取得・差分・AIタグ・ビルドの各スクリプト
- `templates/` — Jinja2 テンプレート（XSS対策で autoescape ON）
- `data/subsidies.json` — 永続化されたデータ
- `docs/` — GitHub Pages 公開ディレクトリ（生成物）
- `SECURITY.md` — セキュリティチェックリスト
