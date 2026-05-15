"""共通定数とパス定義。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
TEMPLATES_DIR = ROOT / "templates"

DATA_FILE = DATA_DIR / "subsidies.json"
ROBOTS_LOG = DOCS_DIR / "robots_check.md"

USER_AGENT = "SubsidySiteBot/0.1 (+local-poc)"
REQUEST_TIMEOUT = 30.0
MAX_REDIRECTS = 3
MAX_RECORDS = 50
BODY_MAX_CHARS = 3000

ALLOWED_HOSTS = frozenset({
    "api.jgrants-portal.go.jp",
    "www.jgrants-portal.go.jp",
})

JGRANTS_API_BASE = "https://api.jgrants-portal.go.jp/exp/v1/public"
JGRANTS_SITE_BASE = "https://www.jgrants-portal.go.jp"

# GitHubリポジトリURL。フッターのOSSリンクで使用。
REPO_URL = "https://github.com/kento20020/subsidy-aggregator"

# Cloudflare Worker のエンドポイント (自由入力テキスト → フィルタ値変換)。
# 空文字なら ウィザードは Worker を呼ばずキーワードマッチのみで動作する。
# 例: "https://subsidy-interpret.your-subdomain.workers.dev/interpret"
WORKER_URL = "https://subsidy-interpret.kento-dev.workers.dev/interpret"

# OGP / SNS 共有用のサイトベースURL (末尾スラなし)
SITE_URL = "https://kento20020.github.io/subsidy-aggregator"
SITE_NAME = "補助金まとめ"
SITE_DESCRIPTION = "使える補助金、見逃さない。中小企業の経営者・事業主向けに公募中の補助金を AI が「対象/経費/書類/警告」で構造化。広告・会員登録なし。"
