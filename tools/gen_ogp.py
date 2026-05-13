"""OGP画像 (1200x630 PNG) を docs/og.png に生成する。

実行: python tools/gen_ogp.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "og.png"

WIDTH, HEIGHT = 1200, 630
BG = (10, 108, 181)        # var(--c-accent)
ACCENT = (255, 255, 255)
SUB = (200, 220, 240)

TITLE = "補助金まとめ"
TAGLINE = "読まずに判断できる、公募中の補助金"
BULLETS = [
    "✓ AIが本文から要点を抽出",
    "✓ 広告なし・会員登録不要",
    "✓ 毎朝8時に自動更新",
]

# 日本語フォント候補（Windows / macOS / Linux）
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto-cjk/NotoSansCJK-Bold.ttc",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def main() -> int:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # 左上アクセント矩形
    draw.rounded_rectangle((60, 60, 200, 200), radius=24, fill=ACCENT)
    char_font = _load_font(110)
    bbox = draw.textbbox((0, 0), "補", font=char_font)
    cw = bbox[2] - bbox[0]
    ch = bbox[3] - bbox[1]
    draw.text((130 - cw // 2 - bbox[0], 130 - ch // 2 - bbox[1]), "補", fill=BG, font=char_font)

    # メインタイトル
    title_font = _load_font(96)
    draw.text((240, 80), TITLE, fill=ACCENT, font=title_font)

    # タグライン
    tag_font = _load_font(44)
    draw.text((60, 260), TAGLINE, fill=ACCENT, font=tag_font)

    # 箇条書き
    bullet_font = _load_font(36)
    for i, line in enumerate(BULLETS):
        draw.text((60, 360 + i * 70), line, fill=SUB, font=bullet_font)

    # フッター
    footer_font = _load_font(28)
    draw.text((60, HEIGHT - 60), "kento20020.github.io/subsidy-aggregator", fill=SUB, font=footer_font)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT, "PNG", optimize=True)
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
