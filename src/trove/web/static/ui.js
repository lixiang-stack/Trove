(() => {
  "use strict";

  let readerCleanup = null;

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
        if (count) count.textContent = query ? `${visible} segments matched` : "";
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

  function initReader(root = document) {
    const reader = root.querySelector("[data-reader]");
    if (!reader) {
      if (readerCleanup) {
        readerCleanup();
        readerCleanup = null;
      }
      return;
    }
    if (reader.dataset.readerBound === "true") return;
    reader.dataset.readerBound = "true";
    if (readerCleanup) readerCleanup();
    const itemId = reader.dataset.readerItemId;
    const chapter = Number(reader.dataset.readerChapter || 0);
    const savedScroll = Number(reader.dataset.readerScroll || 0);
    if (!window.location.hash && savedScroll > 0) {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo(0, Math.max(0, savedScroll * maxScroll));
    }
    let timer = null;
    const save = (keepalive = false) => {
      const paragraphs = Array.from(reader.querySelectorAll(".paragraph"));
      let paragraph = null;
      paragraphs.forEach((candidate) => {
        if (candidate.getBoundingClientRect().top <= 96) paragraph = candidate;
      });
      if (!paragraph && paragraphs.length) paragraph = paragraphs[0];
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = maxScroll > 0 ? window.scrollY / maxScroll : 0;
      const payload = {
        book_locator: {
          chapter_index: chapter,
          paragraph_index: paragraph
            ? Number((paragraph.id.split("-").pop() || "0"))
            : 0,
          scroll_ratio: Math.min(Math.max(ratio, 0), 1),
        },
      };
      fetch(`/api/items/${encodeURIComponent(itemId)}/progress`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
        keepalive,
      }).catch(() => {});
    };
    const onScroll = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => save(), 800);
    };
    const onPageHide = () => save(true);
    const onVisibility = () => {
      if (document.visibilityState === "hidden") save();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", onPageHide);
    document.addEventListener("visibilitychange", onVisibility);
    readerCleanup = () => {
      window.clearTimeout(timer);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", onPageHide);
      document.removeEventListener("visibilitychange", onVisibility);
    };
    if (!window.location.hash) save();
  }

  function bindConfirmation() {
    document.addEventListener("submit", (event) => {
      const form = event.target.closest("form[data-confirm]");
      if (form && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  }

  function initExportSelection(root = document) {
    const form = root.querySelector("#export-form");
    if (!form || form.dataset.exportBound === "true") return;
    form.dataset.exportBound = "true";
    const boxes = Array.from(root.querySelectorAll("[data-export-check]"));
    const submit = form.querySelector("[data-export-submit]");
    const toggle = form.querySelector("[data-export-select-all]");
    if (!submit || !toggle) return;
    const sync = () => {
      const checked = boxes.filter((box) => box.checked).length;
      submit.disabled = checked === 0;
      toggle.textContent =
        boxes.length > 0 && checked === boxes.length ? "取消全选" : "全选";
    };
    boxes.forEach((box) => box.addEventListener("change", sync));
    toggle.addEventListener("click", () => {
      const selectAll = !boxes.every((box) => box.checked);
      boxes.forEach((box) => { box.checked = selectAll; });
      sync();
    });
    sync();
  }

  function refresh(root, { scroll = false } = {}) {
    initTranscriptSearch(root);
    initSearchHighlights(root);
    initReader(root);
    initExportSelection(root);
    if (scroll) scrollToHash();
  }

  function init() {
    bindConfirmation();
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
