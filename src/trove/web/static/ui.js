(() => {
  "use strict";

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function isCjk(value) {
    return /^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]+$/.test(value);
  }

  function queryTerms(query) {
    const terms = [];
    String(query || "").trim().split(/\s+/).forEach((token) => {
      if (!token) return;
      terms.push(token);
      if (isCjk(token) && token.length > 2) {
        for (let index = 0; index < token.length - 1; index += 1) {
          terms.push(token.slice(index, index + 2));
        }
      }
    });
    return Array.from(new Set(terms)).sort((a, b) => b.length - a.length);
  }

  function originalText(element) {
    if (element.dataset.originalText === undefined) {
      element.dataset.originalText = element.textContent;
    }
    return element.dataset.originalText;
  }

  function highlight(element, terms) {
    const text = originalText(element);
    const active = terms.filter(Boolean);
    if (!active.length) {
      element.textContent = text;
      return;
    }
    const pattern = new RegExp(active.map(escapeRegExp).join("|"), "gi");
    const fragment = document.createDocumentFragment();
    let lastIndex = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > lastIndex) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
      }
      const mark = document.createElement("mark");
      mark.textContent = match[0];
      fragment.appendChild(mark);
      lastIndex = match.index + match[0].length;
      if (match.index === pattern.lastIndex) pattern.lastIndex += 1;
    }
    if (lastIndex < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
    }
    element.replaceChildren(fragment);
  }

  function initTranscriptSearch(root = document) {
    root.querySelectorAll("[data-transcript-search]").forEach((input) => {
      if (input.dataset.bound === "true") return;
      input.dataset.bound = "true";
      const details = input.closest("details") || root;
      const segments = Array.from(details.querySelectorAll("[data-transcript-segment]"));
      const count = details.querySelector("[data-transcript-count]");
      const empty = details.querySelector("[data-transcript-empty]");
      const apply = () => {
        const query = input.value.trim();
        const needle = query.toLocaleLowerCase();
        let visible = 0;
        segments.forEach((segment) => {
          const text = segment.querySelector(".seg-text");
          const matches = !needle || text.textContent.toLocaleLowerCase().includes(needle);
          segment.hidden = !matches;
          if (matches) visible += 1;
          if (text) highlight(text, query ? [query] : []);
        });
        if (count) count.textContent = query ? `${visible} 段匹配` : "";
        if (empty) empty.hidden = !query || visible > 0;
      };
      input.addEventListener("input", apply);
      apply();
    });
  }

  function initSearchHighlights(root = document) {
    root.querySelectorAll("[data-search-query]").forEach((region) => {
      const terms = queryTerms(region.dataset.searchQuery);
      region.querySelectorAll(".result-snippet").forEach((snippet) => {
        highlight(snippet, terms);
      });
    });
  }

  function scrollToHash() {
    const hash = window.location.hash;
    if (!hash || hash.length < 2) return;
    let target;
    try {
      target = document.querySelector(hash);
    } catch (_error) {
      return;
    }
    if (!target) return;
    const details = target.closest("details");
    if (details) details.open = true;
    target.scrollIntoView({ block: "center" });
    target.classList.add("is-focused");
    window.setTimeout(() => target.classList.remove("is-focused"), 2400);
  }

  function refresh(root, { scroll = false } = {}) {
    initTranscriptSearch(root);
    initSearchHighlights(root);
    if (scroll) scrollToHash();
  }

  function init() {
    refresh(document, { scroll: true });
    document.body.addEventListener("htmx:afterSwap", (event) => {
      const target = event.target || document;
      refresh(target, { scroll: target.id === "main" });
    });
    document.body.addEventListener("htmx:afterSettle", (event) => {
      const target = event.target || document;
      refresh(target, { scroll: target.id === "main" });
    });
    document.body.addEventListener("htmx:historyRestore", () => {
      refresh(document, { scroll: true });
    });
    window.addEventListener("hashchange", scrollToHash);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
