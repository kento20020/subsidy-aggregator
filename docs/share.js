/**
 * 共有ボタン: 「URLをコピー」ハンドラ
 * - data-share-url のURLをクリップボードに書き込む
 * - 失敗時はテキスト選択フォールバック
 */
(function () {
  "use strict";

  var buttons = document.querySelectorAll(".share-copy");
  if (!buttons.length) return;

  function setCopied(btn) {
    var original = btn.textContent;
    btn.textContent = "コピーしました";
    btn.classList.add("copied");
    setTimeout(function () {
      btn.textContent = original;
      btn.classList.remove("copied");
    }, 1800);
  }

  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var url = btn.getAttribute("data-share-url") || window.location.href;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(
          function () { setCopied(btn); },
          function () { fallbackCopy(url, btn); }
        );
      } else {
        fallbackCopy(url, btn);
      }
    });
  });

  function fallbackCopy(text, btn) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(btn);
    } catch (e) {
      window.prompt("コピーしてください:", text);
    }
  }
})();
