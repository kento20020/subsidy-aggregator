/**
 * 既読カードのトラッキング
 * - 詳細リンク（subsidies/...html）クリック時にカードIDをlocalStorageに保存
 * - 一覧再訪時にカードに `visited` クラスを付与してグレーアウト
 * - 「未読のみ表示」トグルで visited カードを非表示
 * - 「既読をリセット」ボタンで保存内容クリア
 */
(function () {
  "use strict";

  var STORAGE_KEY = "subsidy_visited_v1";
  var MAX_VISITED = 1000;  // localStorage膨張防止

  function load() {
    try {
      var s = localStorage.getItem(STORAGE_KEY);
      return s ? JSON.parse(s) : [];
    } catch (e) { return []; }
  }

  function save(arr) {
    try {
      // 末尾優先で MAX_VISITED 件まで保持
      var trimmed = arr.slice(-MAX_VISITED);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
    } catch (e) { /* quota full or disabled */ }
  }

  function markVisited(id) {
    if (!id) return;
    var arr = load();
    if (arr.indexOf(id) !== -1) return;
    arr.push(id);
    save(arr);
  }

  function applyVisitedClasses() {
    var visited = load();
    var set = {};
    visited.forEach(function (id) { set[id] = true; });
    var cards = document.querySelectorAll(".card");
    var count = 0;
    cards.forEach(function (card) {
      var id = card.dataset.id || "";
      if (set[id]) {
        card.classList.add("visited");
        count++;
      } else {
        card.classList.remove("visited");
      }
    });
    var countEl = document.getElementById("visited-count");
    if (countEl) countEl.textContent = count;
  }

  // ---- 一覧ページ向け ----
  var cardList = document.getElementById("results");
  if (cardList) {
    // クリック時にid記録 (event delegation)
    cardList.addEventListener("click", function (ev) {
      var link = ev.target.closest("a[href^='subsidies/']");
      if (!link) return;
      var card = link.closest(".card");
      if (!card) return;
      markVisited(card.dataset.id);
    });
    applyVisitedClasses();

    // 「未読のみ表示」トグル
    var unreadToggle = document.getElementById("unread-only");
    if (unreadToggle) {
      unreadToggle.addEventListener("change", function () {
        document.body.classList.toggle("hide-visited", unreadToggle.checked);
      });
    }

    // 「既読をリセット」ボタン
    var resetBtn = document.getElementById("reset-visited");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        if (!confirm("既読履歴をすべて消しますか？")) return;
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
        applyVisitedClasses();
      });
    }
  }

  // ---- 詳細ページ向け: 開いたページのidを記録 ----
  var detailRoot = document.querySelector("article.detail");
  if (detailRoot) {
    // URLパスから id を抽出: /subsidies/jgrants-S-00000000.html
    var path = window.location.pathname;
    var m = path.match(/([^\/]+)\.html$/);
    if (m) markVisited("jgrants-" + m[1].replace(/^jgrants-/, ""));
  }
})();
