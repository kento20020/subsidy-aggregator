# subsidy-interpret Worker

ユーザーの自由入力テキストを、補助金検索のフィルタ値（業種・規模・用途・地域）に変換する Cloudflare Worker。

GitHub Pages 上のサイトは Anthropic API キーを安全に持てないため、この Worker が中継する。

## セキュリティ設計

- API キーは `wrangler secret` で環境変数として設定し、コードには含めない
- 入力テキストは 200字 まで（長文プロンプトインジェクション緩和）
- レート制限: 1IPあたり 1分10回（コスト爆発防止）
- レスポンスは固定スキーマでサニタイズ（許可値以外は捨てる）
- CORS: 自サイト + localhost のみ許可

## セットアップ

### 前提
- Node.js 18+
- Cloudflare アカウント（無料枠で十分）

### 手順

```powershell
cd worker
npm install
npx wrangler login                # ブラウザでログイン
npx wrangler secret put ANTHROPIC_API_KEY
#   → プロンプトで Anthropic Console から発行したキーを貼る
npx wrangler deploy
#   → 結果に "https://subsidy-interpret.{your-subdomain}.workers.dev" が表示される
```

### 親サイト側の設定

`scraper/config.py` の `WORKER_URL` を deploy で得た URL + `/interpret` に書き換える:

```python
WORKER_URL = "https://subsidy-interpret.your-subdomain.workers.dev/interpret"
```

その後 `python -m scraper.build` で HTML を再生成すると、ウィザードが自由入力で本Workerを呼ぶようになる。

## 動作確認

```powershell
curl -X POST https://subsidy-interpret.your-subdomain.workers.dev/interpret `
  -H "Content-Type: application/json" `
  -H "Origin: https://kento20020.github.io" `
  -d '{"text":"小さなパン屋を夫婦で経営。新しいオーブンを導入したい"}'
```

期待レスポンス:
```json
{"industry":["飲食"],"size":["個人事業主","小規模事業者"],"purpose":["設備投資"],"region":""}
```

## コスト試算

- 1リクエストあたり Haiku 入力150トークン + 出力80トークン ≒ **0.05円**
- 月100ユーザー × 平均1回 = **5円/月**
- レート制限により最悪値も 1IP × 60req/h × 24h ≒ 月3,000円が上限。実用上ほぼゼロ。
