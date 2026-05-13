/**
 * Cloudflare Worker — 自由入力テキストを補助金検索フィルタ値に変換する。
 *
 * セキュリティ・コスト制御:
 *  - 入力テキストは 200字まで
 *  - 1リクエストあたり Anthropic Haiku を1回だけ呼ぶ
 *  - レート制限: IP単位で1分10回 (Worker memory 内のシンプル実装)
 *  - 結果は固定スキーマで返し、選択肢にないものは "その他" にフォールバック
 *  - CORS: GitHub Pages からの fetch を許可
 */

const MODEL_ID = "claude-haiku-4-5";
const MAX_INPUT_CHARS = 200;
const RATE_LIMIT_PER_MIN = 10;

const ALLOWED_INDUSTRIES = ["IT", "製造業", "飲食", "農業", "建設", "小売", "医療", "教育", "全業種"];
const ALLOWED_SIZES = ["個人事業主", "小規模事業者", "中小企業", "大企業", "全規模"];
const ALLOWED_PURPOSES = ["設備投資", "IT導入", "人材育成", "販路開拓", "研究開発", "省エネ", "海外展開"];
const ALLOWED_REGIONS = ["北海道", "東北", "関東", "中部", "近畿", "中国", "四国", "九州", "沖縄", "全国"];

const SYSTEM_PROMPT = `あなたは日本の補助金検索アシスタント。ユーザーの自然言語の事業紹介を、定型フィルタ値に正規化してください。
回答は厳格なJSONのみ。マークダウン・コードブロック・説明文・追加プロパティ禁止。

スキーマ:
{
  "industry": ["IT","製造業","飲食","農業","建設","小売","医療","教育","全業種" のうち該当0〜3個],
  "size": ["個人事業主","小規模事業者","中小企業","大企業","全規模" のうち該当0〜2個],
  "purpose": ["設備投資","IT導入","人材育成","販路開拓","研究開発","省エネ","海外展開" のうち該当0〜3個],
  "region": "北海道|東北|関東|中部|近畿|中国|四国|九州|沖縄|全国 のうち1個 または 空文字"
}

例:
"小さなパン屋を夫婦で経営。新しいオーブンを導入したい" →
{"industry":["飲食"],"size":["個人事業主","小規模事業者"],"purpose":["設備投資"],"region":""}

不明な場合は空配列・空文字を返す。決して推測で値を足さない。`;

// IPごとのレート制限 (シンプル実装、Worker isolate内で完結)
const rateLimitMap = new Map();

function getRateKey(request) {
  return request.headers.get("CF-Connecting-IP") || "anon";
}

function checkRateLimit(key) {
  const now = Date.now();
  const windowStart = now - 60_000;
  const arr = (rateLimitMap.get(key) || []).filter((t) => t > windowStart);
  if (arr.length >= RATE_LIMIT_PER_MIN) return false;
  arr.push(now);
  rateLimitMap.set(key, arr);
  return true;
}

function corsHeaders(origin) {
  // 明示的に許可するoriginのみエコー (ワイルドカードは避ける)
  const allowed = [
    "https://kento20020.github.io",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
  ];
  const ok = allowed.includes(origin) ? origin : "https://kento20020.github.io";
  return {
    "Access-Control-Allow-Origin": ok,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function jsonResponse(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...corsHeaders(origin),
    },
  });
}

function filterValues(arr, allowed, max) {
  if (!Array.isArray(arr)) return [];
  return arr.filter((v) => typeof v === "string" && allowed.includes(v)).slice(0, max);
}

function filterRegion(value) {
  return typeof value === "string" && ALLOWED_REGIONS.includes(value) ? value : "";
}

async function callClaude(text, apiKey) {
  const body = {
    model: MODEL_ID,
    max_tokens: 256,
    system: SYSTEM_PROMPT,
    messages: [{ role: "user", content: text }],
  };
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`anthropic ${res.status}`);
  const payload = await res.json();
  const raw = (payload.content?.[0]?.text || "").trim();
  // コードブロック除去
  const cleaned = raw.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "");
  return JSON.parse(cleaned);
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== "POST") {
      return jsonResponse({ error: "method not allowed" }, 405, origin);
    }
    if (url.pathname !== "/interpret") {
      return jsonResponse({ error: "not found" }, 404, origin);
    }
    if (!env.ANTHROPIC_API_KEY) {
      return jsonResponse({ error: "server misconfiguration" }, 500, origin);
    }

    if (!checkRateLimit(getRateKey(request))) {
      return jsonResponse({ error: "rate limited" }, 429, origin);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return jsonResponse({ error: "invalid json" }, 400, origin);
    }
    const text = typeof payload.text === "string" ? payload.text.trim() : "";
    if (!text) return jsonResponse({ error: "empty text" }, 400, origin);
    if (text.length > MAX_INPUT_CHARS) {
      return jsonResponse({ error: "text too long" }, 400, origin);
    }

    let result;
    try {
      result = await callClaude(text, env.ANTHROPIC_API_KEY);
    } catch (e) {
      return jsonResponse({ error: "ai failure" }, 502, origin);
    }

    const sanitized = {
      industry: filterValues(result.industry, ALLOWED_INDUSTRIES, 3),
      size: filterValues(result.size, ALLOWED_SIZES, 2),
      purpose: filterValues(result.purpose, ALLOWED_PURPOSES, 3),
      region: filterRegion(result.region),
    };
    return jsonResponse(sanitized, 200, origin);
  },
};
