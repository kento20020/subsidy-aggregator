/**
 * オンボーディング・ウィザード
 * - 初回訪問時に4問のQ&Aを表示
 * - 各問: 3〜5択 + 任意の自由入力欄
 * - 自由入力は Worker (本番) または キーワードマッチ (fallback) で解釈
 * - 完了したら filter.js が読む localStorage を書き換えて再描画
 */
(function () {
  "use strict";

  var modal = document.getElementById("wizard-modal");
  if (!modal) return;

  var WIZARD_DONE_KEY = "subsidy_wizard_done_v1";
  var FILTER_STORAGE_KEY = "subsidy_filters_v1";

  var workerUrl = (document.querySelector('meta[name="subsidy-worker-url"]') || {}).content || "";

  // ---- 47都道府県 → 地方マッピング (Worker出力との突合用) ----
  var REGION_TO_PREFS = {
    "北海道": ["北海道"],
    "東北": ["青森県","岩手県","宮城県","秋田県","山形県","福島県"],
    "関東": ["茨城県","栃木県","群馬県","埼玉県","千葉県","東京都","神奈川県"],
    "中部": ["新潟県","富山県","石川県","福井県","山梨県","長野県","岐阜県","静岡県","愛知県"],
    "近畿": ["三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県"],
    "中国": ["鳥取県","島根県","岡山県","広島県","山口県"],
    "四国": ["徳島県","香川県","愛媛県","高知県"],
    "九州": ["福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県"],
    "沖縄": ["沖縄県"]
  };

  // ---- キーワード辞書（フォールバック用）----
  var INDUSTRY_KEYWORDS = {
    "IT": ["IT","ソフト","アプリ","Web","クラウド","SaaS","AI","DX","エンジニア","システム","プログラム"],
    "製造業": ["製造","ものづくり","工場","メーカー","加工","機械","金属","電子部品","町工場"],
    "飲食": ["飲食","レストラン","パン","パン屋","カフェ","居酒屋","食堂","ラーメン","料理"],
    "農業": ["農業","農家","農産","畑","果樹","畜産","酪農","漁業","水産"],
    "建設": ["建設","建築","土木","工務","リフォーム","内装"],
    "小売": ["小売","店舗","販売","EC","通販","物販","アパレル"],
    "医療": ["医療","病院","クリニック","介護","薬局","訪問看護"],
    "教育": ["教育","学校","塾","保育","スクール","研修"]
  };
  var SIZE_KEYWORDS = {
    "個人事業主": ["個人","フリーランス","ひとり","一人","夫婦","家族経営"],
    "小規模事業者": ["小規模","小さな","少人数","数人","5人","10人"],
    "中小企業": ["中小企業","中小","50人","100人"],
    "大企業": ["大企業","大手","数百人","1000人"]
  };
  var PURPOSE_KEYWORDS = {
    "設備投資": ["設備","機械","装置","オーブン","工作機","車両","購入"],
    "IT導入": ["IT","システム","ソフト","クラウド","DX","デジタル"],
    "人材育成": ["人材","研修","教育","採用","雇用"],
    "販路開拓": ["販路","営業","集客","販売","マーケ","広告"],
    "研究開発": ["研究","開発","R&D","新製品","試作"],
    "省エネ": ["省エネ","脱炭素","太陽光","断熱","環境"],
    "海外展開": ["海外","輸出","越境EC","インバウンド"]
  };
  var REGION_KEYWORDS_RAW = {
    "北海道": ["北海道","札幌"],
    "東北": ["東北","青森","岩手","宮城","秋田","山形","福島","仙台"],
    "関東": ["関東","東京","埼玉","千葉","神奈川","茨城","栃木","群馬","横浜"],
    "中部": ["中部","愛知","名古屋","静岡","新潟","長野","富山","石川","福井","岐阜","山梨"],
    "近畿": ["近畿","関西","大阪","京都","兵庫","奈良","滋賀","和歌山","神戸"],
    "中国": ["中国地方","岡山","広島","山口","島根","鳥取"],
    "四国": ["四国","徳島","香川","愛媛","高知"],
    "九州": ["九州","福岡","佐賀","長崎","熊本","大分","宮崎","鹿児島"],
    "沖縄": ["沖縄","那覇","琉球"]
  };

  function keywordExtract(text) {
    function pickFrom(dict, max) {
      var out = [];
      for (var key in dict) {
        if (out.length >= max) break;
        var ws = dict[key];
        for (var i = 0; i < ws.length; i++) {
          if (text.indexOf(ws[i]) !== -1) { out.push(key); break; }
        }
      }
      return out;
    }
    var region = "";
    for (var r in REGION_KEYWORDS_RAW) {
      var found = false;
      for (var j = 0; j < REGION_KEYWORDS_RAW[r].length; j++) {
        if (text.indexOf(REGION_KEYWORDS_RAW[r][j]) !== -1) { region = r; found = true; break; }
      }
      if (found) break;
    }
    return {
      industry: pickFrom(INDUSTRY_KEYWORDS, 3),
      size: pickFrom(SIZE_KEYWORDS, 2),
      purpose: pickFrom(PURPOSE_KEYWORDS, 3),
      region: region
    };
  }

  async function interpretFreeText(text) {
    if (!text || !text.trim()) return null;
    if (!workerUrl) return keywordExtract(text);
    try {
      var res = await fetch(workerUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.slice(0, 200) }),
        mode: "cors"
      });
      if (!res.ok) return keywordExtract(text);
      var data = await res.json();
      return {
        industry: Array.isArray(data.industry) ? data.industry : [],
        size: Array.isArray(data.size) ? data.size : [],
        purpose: Array.isArray(data.purpose) ? data.purpose : [],
        region: typeof data.region === "string" ? data.region : ""
      };
    } catch (e) {
      return keywordExtract(text);
    }
  }

  // ---- 質問定義 ----
  var QUESTIONS = [
    {
      id: "region",
      label: "事業の拠点は？",
      type: "single",
      options: ["北海道","東北","関東","中部","近畿","中国","四国","九州","沖縄","全国どこでも"],
      freeHint: "例: 東京都台東区"
    },
    {
      id: "industry",
      label: "業種は？",
      type: "single",
      options: ["IT・ソフト","製造業","飲食・サービス","農業・漁業","建設","小売・流通","医療・介護","教育","その他"],
      freeHint: "例: 町のパン屋"
    },
    {
      id: "size",
      label: "事業規模は？",
      type: "single",
      options: ["個人事業主","小規模事業者(〜20人)","中小企業(〜300人)","大企業","こだわらない"],
      freeHint: "例: 夫婦と社員3人"
    },
    {
      id: "purpose",
      label: "何に使いたい？",
      type: "single",
      options: ["設備投資","IT導入","人材育成","販路開拓","研究開発","省エネ","海外展開","まだ決まっていない"],
      freeHint: "例: 新しいオーブンを買いたい"
    }
  ];

  // 選択肢ラベル → フィルタ値マッピング
  var INDUSTRY_LABEL_TO_VALUE = {
    "IT・ソフト": "IT",
    "製造業": "製造業",
    "飲食・サービス": "飲食",
    "農業・漁業": "農業",
    "建設": "建設",
    "小売・流通": "小売",
    "医療・介護": "医療",
    "教育": "教育",
    "その他": null
  };
  var SIZE_LABEL_TO_VALUE = {
    "個人事業主": "個人事業主",
    "小規模事業者(〜20人)": "小規模事業者",
    "中小企業(〜300人)": "中小企業",
    "大企業": "大企業",
    "こだわらない": null
  };
  var PURPOSE_LABEL_TO_VALUE = {
    "設備投資": "設備投資",
    "IT導入": "IT導入",
    "人材育成": "人材育成",
    "販路開拓": "販路開拓",
    "研究開発": "研究開発",
    "省エネ": "省エネ",
    "海外展開": "海外展開",
    "まだ決まっていない": null
  };

  // ---- 状態 ----
  var state = {
    step: 0,
    answers: { region: null, industry: null, size: null, purpose: null },
    freeTexts: { region: "", industry: "", size: "", purpose: "" }
  };

  // ---- DOM helper ----
  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "class") e.className = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    if (children) children.forEach(function (c) { e.appendChild(c); });
    return e;
  }

  function renderStep() {
    var body = modal.querySelector(".wizard-body");
    body.innerHTML = "";
    var q = QUESTIONS[state.step];

    var heading = el("div", { class: "wizard-step" }, [
      el("p", { class: "wizard-progress", text: "Q" + (state.step + 1) + " / " + QUESTIONS.length }),
      el("h2", { text: q.label }),
    ]);
    body.appendChild(heading);

    var opts = el("div", { class: "wizard-options" });
    q.options.forEach(function (opt) {
      var btn = el("button", { type: "button", class: "wizard-option" + (state.answers[q.id] === opt ? " selected" : "") });
      btn.textContent = opt;
      btn.addEventListener("click", function () {
        state.answers[q.id] = (state.answers[q.id] === opt) ? null : opt;
        renderStep();
      });
      opts.appendChild(btn);
    });
    body.appendChild(opts);

    var freeWrap = el("div", { class: "wizard-free" });
    freeWrap.appendChild(el("label", { class: "wizard-free-label", text: "または自由に入力 (任意・200字以内)" }));
    var input = el("input", { type: "text", maxlength: "200", placeholder: q.freeHint, class: "wizard-free-input" });
    input.value = state.freeTexts[q.id] || "";
    input.addEventListener("input", function () {
      state.freeTexts[q.id] = input.value;
    });
    freeWrap.appendChild(input);
    body.appendChild(freeWrap);

    // ナビゲーション
    modal.querySelector(".wizard-back").disabled = state.step === 0;
    var nextBtn = modal.querySelector(".wizard-next");
    if (state.step === QUESTIONS.length - 1) {
      nextBtn.textContent = "結果を見る";
    } else {
      nextBtn.textContent = "次へ →";
    }
  }

  // ---- 適用処理 ----
  function labelToValue(qid, label) {
    if (qid === "industry") return INDUSTRY_LABEL_TO_VALUE[label] || null;
    if (qid === "size") return SIZE_LABEL_TO_VALUE[label] || null;
    if (qid === "purpose") return PURPOSE_LABEL_TO_VALUE[label] || null;
    return null;
  }

  function applyRegionToPrefecture(region) {
    // ウィザードの「地域」は地方単位 → filter.js の prefecture は単一都道府県 + "全国"
    // 都道府県を完全に絞り込むには 1県を指定する必要があるが、地方単位だと複数あるため
    // PoCでは: "全国どこでも" or "関東" 等の場合は filter prefecture を "all"のままにし、
    // カードのprefectureが「全国」のものに加えて地方内都道府県を含むよう、別フィルタ用意せず
    // ひとまず "all" にする。将来 filter.js を拡張して地方フィルタ対応。
    if (!region || region === "全国どこでも" || region === "全国") return "all";
    // PoCでは地方→都道府県の絞り込みは複雑なので "all" にして警告UIだけで誘導
    return "all";
  }

  async function buildFilterStateFromWizard() {
    // 出発点: 現在のlocalStorageの選択（既存なら）に「ウィザードの結果」を上書き
    var current = {};
    try {
      var saved = localStorage.getItem(FILTER_STORAGE_KEY);
      if (saved) current = JSON.parse(saved);
    } catch (e) { /* ignore */ }

    var industry = [];
    var size = [];
    var purpose = [];
    var prefecture = "all";

    // 選択肢
    var iv = labelToValue("industry", state.answers.industry);
    if (iv) industry.push(iv);
    var sv = labelToValue("size", state.answers.size);
    if (sv) size.push(sv);
    var pv = labelToValue("purpose", state.answers.purpose);
    if (pv) purpose.push(pv);

    // 自由入力 → Worker / Keyword
    var allFreeText = [
      state.freeTexts.region,
      state.freeTexts.industry,
      state.freeTexts.size,
      state.freeTexts.purpose
    ].filter(function (s) { return s && s.trim(); }).join(" / ").slice(0, 200);

    if (allFreeText) {
      var interp = await interpretFreeText(allFreeText);
      if (interp) {
        interp.industry.forEach(function (v) { if (industry.indexOf(v) === -1) industry.push(v); });
        interp.size.forEach(function (v) { if (size.indexOf(v) === -1) size.push(v); });
        interp.purpose.forEach(function (v) { if (purpose.indexOf(v) === -1) purpose.push(v); });
      }
    }

    return {
      industry: industry,
      size: size,
      purpose: purpose,
      prefecture: prefecture,
      deadline: current.deadline || "all",
      sort: current.sort || "new"
    };
  }

  function applyState(state) {
    // チェックボックス
    document.querySelectorAll('input[type="checkbox"][data-filter]').forEach(function (cb) {
      var kind = cb.dataset.filter;
      var arr = state[kind] || [];
      cb.checked = arr.indexOf(cb.value) !== -1;
    });
    var prefSel = document.getElementById("filter-prefecture");
    if (prefSel) prefSel.value = state.prefecture || "all";
    var deadSel = document.getElementById("filter-deadline");
    if (deadSel) deadSel.value = state.deadline || "all";
    var sortSel = document.getElementById("sort-order");
    if (sortSel) sortSel.value = state.sort || "new";

    // filter.js が listen している change を発火 → 再描画 & 永続化
    var changeEvt;
    try { changeEvt = new Event("change", { bubbles: true }); } catch (e) { changeEvt = document.createEvent("Event"); changeEvt.initEvent("change", true, true); }
    if (prefSel) prefSel.dispatchEvent(changeEvt);
    if (deadSel) deadSel.dispatchEvent(changeEvt);
    // checkboxは1個変えれば applyFilters が走るので最初の1個に発火
    var firstCb = document.querySelector('input[type="checkbox"][data-filter]');
    if (firstCb) firstCb.dispatchEvent(changeEvt);
  }

  // ---- 表示制御 ----
  function show() {
    modal.classList.remove("hidden");
    document.body.classList.add("wizard-open");
    state.step = 0;
    renderStep();
  }

  function hide() {
    modal.classList.add("hidden");
    document.body.classList.remove("wizard-open");
  }

  // ---- イベントバインド ----
  modal.querySelector(".wizard-back").addEventListener("click", function () {
    if (state.step > 0) { state.step--; renderStep(); }
  });

  modal.querySelector(".wizard-next").addEventListener("click", async function () {
    if (state.step < QUESTIONS.length - 1) {
      state.step++;
      renderStep();
      return;
    }
    // 完了
    var btn = this;
    btn.disabled = true;
    btn.textContent = "解析中…";
    var fs = await buildFilterStateFromWizard();
    applyState(fs);
    try { localStorage.setItem(WIZARD_DONE_KEY, "1"); } catch (e) {}
    btn.disabled = false;
    btn.textContent = "結果を見る";
    hide();
  });

  modal.querySelector(".wizard-skip").addEventListener("click", function () {
    try { localStorage.setItem(WIZARD_DONE_KEY, "1"); } catch (e) {}
    hide();
  });

  var openBtn = document.getElementById("open-wizard");
  if (openBtn) {
    openBtn.addEventListener("click", function (e) {
      e.preventDefault();
      show();
    });
  }

  // ---- 初期表示判定 ----
  var done = false;
  try { done = !!localStorage.getItem(WIZARD_DONE_KEY); } catch (e) {}
  // URLクエリがあれば共有リンク経由なのでウィザード出さない
  if (!done && !window.location.search) {
    show();
  }
})();
