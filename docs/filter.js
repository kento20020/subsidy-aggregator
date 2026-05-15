(function () {
  "use strict";

  var results = document.getElementById("results");
  if (!results) return;

  var noMatch = document.getElementById("no-match");
  var deadlineSelect = document.getElementById("filter-deadline");
  var prefSelect = document.getElementById("filter-prefecture");
  var sortSelect = document.getElementById("sort-order");
  var resetBtn = document.getElementById("reset-filters");
  var copyBtn = document.getElementById("copy-link");
  var tagCheckboxes = document.querySelectorAll('input[type="checkbox"][data-filter]');

  var STORAGE_KEY = "subsidy_filters_v1";
  var NATIONWIDE = ["全国", "全都道府県", ""];

  function isNationwide(cardPref) {
    return NATIONWIDE.indexOf(cardPref) !== -1;
  }

  function matchesPrefecture(cardPref, selected) {
    if (!selected || selected === "all") return true;
    if (selected === "全国") return isNationwide(cardPref);
    return cardPref === selected || isNationwide(cardPref);
  }

  function getSelected(kind) {
    var out = [];
    tagCheckboxes.forEach(function (cb) {
      if (cb.dataset.filter === kind && cb.checked) out.push(cb.value);
    });
    return out;
  }

  function matchesTag(cardValues, selected) {
    if (selected.length === 0) return true;
    var arr = cardValues.split(",").filter(Boolean);
    for (var i = 0; i < selected.length; i++) {
      if (arr.indexOf(selected[i]) !== -1) return true;
    }
    return false;
  }

  // Phase 1 (TECH_DEF §1.1): industry は universal フィールドの特別扱い
  function matchesIndustry(card, selected) {
    if (selected.length === 0) return true;
    if (card.dataset.industryUniversal === "true") return true; // 全業種対象は常にマッチ
    var arr = (card.dataset.industry || "").split(",").filter(Boolean);
    for (var i = 0; i < selected.length; i++) {
      if (arr.indexOf(selected[i]) !== -1) return true;
    }
    return false;
  }

  // Phase 2 (TECH_DEF §1.2): size は universal フィールドの特別扱い
  function matchesSize(card, selected) {
    if (selected.length === 0) return true;
    if (card.dataset.sizeUniversal === "true") return true; // 全規模対象は常にマッチ
    var arr = (card.dataset.size || "").split(",").filter(Boolean);
    for (var i = 0; i < selected.length; i++) {
      if (arr.indexOf(selected[i]) !== -1) return true;
    }
    return false;
  }

  function withinDeadline(deadlineStr, days) {
    if (days === "all" || !deadlineStr) return days === "all";
    var d = new Date(deadlineStr + "T23:59:59Z");
    if (isNaN(d.getTime())) return false;
    var diffMs = d.getTime() - Date.now();
    var diffDays = diffMs / (1000 * 60 * 60 * 24);
    return diffDays >= 0 && diffDays <= parseInt(days, 10);
  }

  // --- State persistence (URL query > localStorage > defaults) ---

  function readUIState() {
    return {
      industry: getSelected("industry"),
      size: getSelected("size"),
      purpose: getSelected("purpose"),
      prefecture: prefSelect ? prefSelect.value : "all",
      deadline: deadlineSelect ? deadlineSelect.value : "all",
      sort: sortSelect ? sortSelect.value : "new"
    };
  }

  function stateToParams(state) {
    var params = new URLSearchParams();
    if (state.industry && state.industry.length) params.set("industry", state.industry.join(","));
    if (state.size && state.size.length) params.set("size", state.size.join(","));
    if (state.purpose && state.purpose.length) params.set("purpose", state.purpose.join(","));
    if (state.prefecture && state.prefecture !== "all") params.set("prefecture", state.prefecture);
    if (state.deadline && state.deadline !== "all") params.set("deadline", state.deadline);
    if (state.sort && state.sort !== "new") params.set("sort", state.sort);
    return params;
  }

  function paramsToState(params) {
    return {
      industry: (params.get("industry") || "").split(",").filter(Boolean),
      size: (params.get("size") || "").split(",").filter(Boolean),
      purpose: (params.get("purpose") || "").split(",").filter(Boolean),
      prefecture: params.get("prefecture") || "all",
      deadline: params.get("deadline") || "all",
      sort: params.get("sort") || "new"
    };
  }

  function loadInitialState() {
    // 優先順位: URL > localStorage > null(=デフォルト)
    var url = new URL(window.location.href);
    if (url.searchParams.toString()) {
      return paramsToState(url.searchParams);
    }
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch (e) { /* localStorage disabled/corrupted */ }
    return null;
  }

  function applyState(state) {
    if (!state) return;
    function setChecks(kind, values) {
      var arr = values || [];
      tagCheckboxes.forEach(function (cb) {
        if (cb.dataset.filter === kind) cb.checked = arr.indexOf(cb.value) !== -1;
      });
    }
    setChecks("industry", state.industry);
    setChecks("size", state.size);
    setChecks("purpose", state.purpose);
    if (prefSelect && state.prefecture) prefSelect.value = state.prefecture;
    if (deadlineSelect && state.deadline) deadlineSelect.value = state.deadline;
    if (sortSelect && state.sort) sortSelect.value = state.sort;
  }

  // URL書き換え時に保持する未知パラメータ (他JSが使うもの)
  var FOREIGN_KEYS_TO_PRESERVE = ["wizard"];

  function persistState() {
    var state = readUIState();
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) { /* quota full or disabled */ }
    var params = stateToParams(state);

    // 自分が管理しないクエリ (例: wizard=1) は維持する
    var existing = new URLSearchParams(window.location.search);
    FOREIGN_KEYS_TO_PRESERVE.forEach(function (key) {
      if (existing.has(key)) params.set(key, existing.get(key));
    });

    var qs = params.toString();
    var newUrl = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
    try {
      history.replaceState(null, "", newUrl);
    } catch (e) { /* sandbox or file://: ignore */ }
  }

  // --- Filter / Sort ---

  function applyFilters() {
    var industries = getSelected("industry");
    var sizes = getSelected("size");
    var purposes = getSelected("purpose");
    var deadlineMode = deadlineSelect ? deadlineSelect.value : "all";
    var prefMode = prefSelect ? prefSelect.value : "all";

    var cards = results.querySelectorAll(".card");
    var visibleCount = 0;
    cards.forEach(function (card) {
      var ok =
        matchesIndustry(card, industries) &&
        matchesSize(card, sizes) &&
        matchesTag(card.dataset.purpose || "", purposes) &&
        matchesPrefecture(card.dataset.prefecture || "", prefMode) &&
        withinDeadline(card.dataset.deadline || "", deadlineMode);
      card.classList.toggle("hidden", !ok);
      if (ok) visibleCount++;
    });

    if (noMatch) noMatch.classList.toggle("hidden", visibleCount !== 0 || cards.length === 0);
    applySort();
    persistState();
  }

  function applySort() {
    if (!sortSelect) return;
    var mode = sortSelect.value;
    var cards = Array.prototype.slice.call(results.querySelectorAll(".card"));
    cards.sort(function (a, b) {
      if (mode === "deadline") {
        var da = a.dataset.deadline || "9999-12-31";
        var db = b.dataset.deadline || "9999-12-31";
        return da.localeCompare(db);
      }
      if (mode === "amount") {
        return parseInt(b.dataset.amountMax || "0", 10) - parseInt(a.dataset.amountMax || "0", 10);
      }
      var fa = a.dataset.firstSeen || "";
      var fb = b.dataset.firstSeen || "";
      return fb.localeCompare(fa);
    });
    cards.forEach(function (c) { results.appendChild(c); });
  }

  // --- Event wiring ---

  tagCheckboxes.forEach(function (cb) { cb.addEventListener("change", applyFilters); });
  if (deadlineSelect) deadlineSelect.addEventListener("change", applyFilters);
  if (prefSelect) prefSelect.addEventListener("change", applyFilters);
  if (sortSelect) sortSelect.addEventListener("change", function () { applySort(); persistState(); });

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      tagCheckboxes.forEach(function (cb) { cb.checked = false; });
      if (deadlineSelect) deadlineSelect.value = "all";
      if (prefSelect) prefSelect.value = "all";
      if (sortSelect) sortSelect.value = "new";
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      try { history.replaceState(null, "", window.location.pathname); } catch (e) {}
      applyFilters();
    });
  }

  if (copyBtn) {
    var originalLabel = copyBtn.textContent;
    copyBtn.addEventListener("click", function () {
      var url = window.location.href;
      var done = function (ok) {
        copyBtn.textContent = ok ? "コピーしました ✓" : "コピー失敗";
        copyBtn.classList.toggle("copied", ok);
        setTimeout(function () {
          copyBtn.textContent = originalLabel;
          copyBtn.classList.remove("copied");
        }, 1800);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { done(true); }, function () { done(false); });
      } else {
        // フォールバック: 旧API
        try {
          var ta = document.createElement("textarea");
          ta.value = url;
          ta.setAttribute("readonly", "");
          ta.style.position = "absolute";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          var ok = document.execCommand("copy");
          document.body.removeChild(ta);
          done(ok);
        } catch (e) { done(false); }
      }
    });
  }

  // --- Init ---

  var initial = loadInitialState();
  if (initial) {
    applyState(initial);
    applyFilters();  // 復元値で再描画＆URL同期
  } else {
    applySort();
  }
})();
