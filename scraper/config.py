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

# GitHubリポジトリURL（公開後に書き換える。未定なら # でフッター無効化）
REPO_URL = "#"
