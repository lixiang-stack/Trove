(() => {
  "use strict";

  const SPEEDS = [1, 1.25, 1.5, 2];
  const SAVE_INTERVAL_MS = 5000;
  const STORAGE_KEY = "trove.lastItem";

  const state = {
    item: null,
    playing: false,
    speed: 1,
    saveTimer: null,
    pendingSeek: null,
    manualFinished: false,
  };

  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function $all(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function audio() {
    return $("#global-audio");
  }

  function fmt(seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const rest = value % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
      : `${minutes}:${String(rest).padStart(2, "0")}`;
  }

  function showError(message) {
    const element = $("#player-error");
    if (!element) return;
    element.textContent = message;
    element.hidden = false;
    window.clearTimeout(showError.timer);
    showError.timer = window.setTimeout(() => { element.hidden = true; }, 3200);
  }

  function itemFromDataset(button) {
    return {
      id: button.dataset.itemId,
      title: button.dataset.title || "Untitled content",
      author: button.dataset.author || "",
      audio_url: button.dataset.audioUrl,
      position: Number(button.dataset.position || 0),
      duration: Number(button.dataset.duration || 0),
      listen_url: button.dataset.listenUrl || `/items/${button.dataset.itemId}/listen`,
    };
  }

  function itemFromScript(script) {
    try {
      return JSON.parse(script.textContent);
    } catch (_error) {
      return null;
    }
  }

  function persistedItem() {
    try {
      return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
    } catch (_error) {
      return null;
    }
  }

  function persistItem(item) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(item));
    } catch (_error) {
      /* private mode */
    }
  }

  function setMediaSession(item) {
    if (!("mediaSession" in navigator) || typeof MediaMetadata === "undefined") return;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: item.title,
        artist: item.author || "Trove",
        album: "Trove",
      });
      const player = audio();
      const actions = {
        play: () => player.play(),
        pause: () => player.pause(),
        seekbackward: (details) => { player.currentTime = Math.max(0, player.currentTime - (details.seekOffset || 10)); },
        seekforward: (details) => { player.currentTime = Math.min(player.duration || Infinity, player.currentTime + (details.seekOffset || 10)); },
        seekto: (details) => { if (typeof details.seekTime === "number") player.currentTime = details.seekTime; },
      };
      Object.entries(actions).forEach(([action, handler]) => {
        try { navigator.mediaSession.setActionHandler(action, handler); } catch (_error) { /* unsupported action */ }
      });
    } catch (_error) {
      /* Media Session is best-effort */
    }
  }

  function updateMediaSessionState() {
    if (!("mediaSession" in navigator)) return;
    try {
      navigator.mediaSession.playbackState = state.playing ? "playing" : "paused";
    } catch (_error) {
      /* noop */
    }
  }

  function updateUI() {
    const player = audio();
    const item = state.item;
    if (!item) return;
    const duration = player.duration && Number.isFinite(player.duration) ? player.duration : (item.duration || 0);
    $all("[data-player-title]").forEach((element) => { element.textContent = item.title; });
    $all("[data-player-meta]").forEach((element) => { element.textContent = item.author || "Trove"; });
    $all("[data-player-current]").forEach((element) => { element.textContent = fmt(player.currentTime); });
    $all("[data-player-duration]").forEach((element) => { element.textContent = fmt(duration); });
    $all("[data-player-icon]").forEach((element) => { element.textContent = state.playing ? "❚❚" : "▶"; });
    $all("[data-player-speed]").forEach((element) => { element.textContent = `${state.speed}×`; });
    $all("[data-player-link]").forEach((element) => { element.setAttribute("href", item.listen_url); });
    $all("[data-player-seek]").forEach((element) => {
      const value = duration > 0 ? Math.round((player.currentTime / duration) * 1000) : 0;
      if (document.activeElement !== element) element.value = String(value);
    });
    $all("[data-inline-for]").forEach((element) => {
      if (element.dataset.inlineFor !== item.id) return;
      const current = $("[data-inline-current]", element);
      const total = $("[data-inline-duration]", element);
      const title = $("[data-inline-title]", element);
      if (current) current.textContent = fmt(player.currentTime);
      if (total) total.textContent = fmt(duration);
      if (title) title.textContent = item.title;
      const seek = $("[data-inline-seek]", element);
      if (seek && document.activeElement !== seek) {
        seek.value = String(duration > 0 ? Math.round((player.currentTime / duration) * 1000) : 0);
      }
    });
    const mini = $("#mini-player");
    if (mini) mini.hidden = false;
  }

  function loadItem(item, { autoplay = false } = {}) {
    const player = audio();
    if (!player || !item || !item.audio_url) return;
    const same = state.item && state.item.id === item.id;
    state.item = { ...state.item, ...item };
    state.manualFinished = false;
    persistItem(state.item);
    setMediaSession(state.item);
    if (!same) {
      state.pendingSeek = Number(item.position || 0);
      player.src = item.audio_url;
      player.playbackRate = state.speed;
      player.load();
      if (state.pendingSeek > 0) {
        const apply = () => {
          if (state.pendingSeek !== null) {
            try { player.currentTime = state.pendingSeek; } catch (_error) { /* metadata not ready */ }
            state.pendingSeek = null;
          }
        };
        player.addEventListener("loadedmetadata", apply, { once: true });
        apply();
      }
    }
    updateUI();
    if (autoplay) {
      player.play().catch(() => showError("The browser blocked autoplay; press play again."));
    }
  }

  function ensureItem() {
    if (state.item) return state.item;
    const persisted = persistedItem();
    if (persisted && persisted.audio_url) {
      state.item = persisted;
      state.speed = Number(persisted.speed || 1);
      return state.item;
    }
    return null;
  }

  function toggle() {
    const player = audio();
    if (!player) return;
    if (!ensureItem()) return;
    if (!player.src) {
      loadItem(state.item, { autoplay: true });
      return;
    }
    if (player.paused) {
      player.play().catch(() => showError("Could not play this audio."));
    } else {
      player.pause();
    }
  }

  function cycleSpeed() {
    const index = SPEEDS.indexOf(state.speed);
    state.speed = SPEEDS[(index + 1) % SPEEDS.length];
    const player = audio();
    if (player) player.playbackRate = state.speed;
    if (state.item) persistItem({ ...state.item, speed: state.speed });
    updateUI();
  }

  function showInline(itemId) {
    $all("[data-inline-for]").forEach((element) => {
      element.hidden = element.dataset.inlineFor !== itemId;
    });
  }

  async function saveProgress(extra = {}, options = {}) {
    const item = state.item;
    const player = audio();
    if (!item || !player || !item.id) return;
    const payload = { position_sec: player.currentTime || 0, ...extra };
    try {
      const response = await fetch(`/api/items/${encodeURIComponent(item.id)}/progress`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
        keepalive: Boolean(options.keepalive),
      });
      if (!response.ok) return;
      const data = await response.json();
      if (data.item) {
        state.item.position = data.item.audio_position_sec;
        state.item.duration = data.item.duration_sec || state.item.duration;
        if (data.item.consumption_state === "finished") state.manualFinished = true;
        persistItem(state.item);
        $all("[data-consumption-badge]").forEach((element) => {
          element.textContent = data.item.consumption_label;
          element.dataset.state = data.item.consumption_state;
        });
      }
    } catch (_error) {
      /* progress saving is best-effort */
    }
  }

  function startSaveTimer() {
    stopSaveTimer();
    state.saveTimer = window.setInterval(() => saveProgress(), SAVE_INTERVAL_MS);
  }

  function stopSaveTimer() {
    if (state.saveTimer) {
      window.clearInterval(state.saveTimer);
      state.saveTimer = null;
    }
  }

  function markFinished() {
    const player = audio();
    if (!player || !state.item) return;
    if (player.duration && Number.isFinite(player.duration)) player.currentTime = player.duration;
    saveProgress({ consumption_state: "finished" });
    state.manualFinished = true;
  }

  function bindAudio() {
    const player = audio();
    if (!player) return;
    player.addEventListener("loadedmetadata", () => updateUI());
    player.addEventListener("timeupdate", () => updateUI());
    player.addEventListener("play", () => {
      state.playing = true;
      updateUI();
      updateMediaSessionState();
      startSaveTimer();
    });
    player.addEventListener("pause", () => {
      state.playing = false;
      updateUI();
      updateMediaSessionState();
      stopSaveTimer();
      saveProgress();
    });
    player.addEventListener("ended", () => {
      state.playing = false;
      stopSaveTimer();
      saveProgress({ consumption_state: "finished" });
      updateUI();
      updateMediaSessionState();
    });
    player.addEventListener("error", () => {
      showError("Failed to load audio; try again later.");
    });
  }

  function bindClicks() {
    document.addEventListener("click", (event) => {
      const playButton = event.target.closest("[data-play-item]");
      if (playButton) {
        event.preventDefault();
        const item = itemFromDataset(playButton);
        const player = audio();
        if (state.item && state.item.id === item.id && player && !player.paused) {
          player.pause();
          return;
        }
        loadItem(item, { autoplay: true });
        showInline(item.id);
        return;
      }
      const actionButton = event.target.closest("[data-player-action]");
      if (actionButton) {
        event.preventDefault();
        const action = actionButton.dataset.playerAction;
        if (action === "toggle") toggle();
        if (action === "speed") cycleSpeed();
        if (action === "finish") markFinished();
      }
    });

    document.addEventListener("input", (event) => {
      const seek = event.target.closest("[data-player-seek], [data-inline-seek]");
      if (!seek) return;
      const player = audio();
      if (!player || !Number.isFinite(player.duration) || player.duration <= 0) return;
      player.currentTime = (Number(seek.value) / 1000) * player.duration;
      updateUI();
    });

    document.addEventListener("change", (event) => {
      const seek = event.target.closest("[data-player-seek], [data-inline-seek]");
      if (seek) saveProgress();
    });
  }

  function refreshNav() {
    const path = window.location.pathname;
    const active = path.startsWith("/search")
      ? "/search"
      : path.startsWith("/add")
        ? "/add"
        : "/library";
    $all(".main-nav a, .bottom-nav a").forEach((link) => {
      link.classList.toggle("active", link.getAttribute("href") === active);
    });
  }

  function refreshPagePlayer() {
    document.body.dataset.page = $(".now-playing") ? "listen" : "app";
    refreshNav();
    const script = $("[data-player-item]");
    if (script) {
      const item = itemFromScript(script);
      if (item) loadItem(item);
      return;
    }
    const persisted = persistedItem();
    if (persisted && persisted.audio_url) {
      state.item = persisted;
      state.speed = Number(persisted.speed || 1);
      updateUI();
    }
  }

  function init() {
    bindAudio();
    bindClicks();
    bindUpload();
    refreshPagePlayer();
    document.body.addEventListener("htmx:afterSwap", (event) => {
      if (event.target && event.target.id === "main") {
        showInline(state.item && state.item.id);
        refreshPagePlayer();
      }
    });
    document.body.addEventListener("htmx:historyRestore", refreshPagePlayer);
    window.addEventListener("popstate", refreshNav);
    window.addEventListener("pagehide", () => {
      if (state.item) saveProgress({}, { keepalive: true });
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden" && state.item) saveProgress();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }


  function bindUpload() {
    const form = document.getElementById("upload-form");
    if (!form) return;
    const progress = document.getElementById("upload-progress");
    const note = document.getElementById("upload-note");
    const input = document.getElementById("upload-input");
    form.addEventListener("submit", (event) => {
      if (!window.XMLHttpRequest || !input || !input.files || !input.files.length) return;
      event.preventDefault();
      const data = new FormData();
      data.append("file", input.files[0]);
      if (progress) {
        progress.hidden = false;
        progress.value = 0;
      }
      if (note) note.textContent = "Uploading…";
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/uploads");
      xhr.upload.addEventListener("progress", (uploadEvent) => {
        if (!uploadEvent.lengthComputable || !progress) return;
        progress.value = Math.round((uploadEvent.loaded / uploadEvent.total) * 100);
        if (note) note.textContent = `Uploading ${progress.value}%`;
      });
      xhr.addEventListener("load", async () => {
        if (xhr.status !== 200) {
          let message = "Upload failed";
          try { message = JSON.parse(xhr.responseText).message || message; } catch (_error) { /* noop */ }
          if (note) note.textContent = message;
          if (progress) progress.hidden = true;
          return;
        }
        const record = JSON.parse(xhr.responseText);
        const response = await fetch("/api/items", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ kind: "upload", upload_id: record.upload_id }),
        });
        if (response.ok) {
          const payload = await response.json();
          window.location.href = `/items/${payload.item.id}`;
          return;
        }
        let message = "Failed to add to library";
        try { message = (await response.json()).message || message; } catch (_error) { /* noop */ }
        if (note) note.textContent = message;
        if (progress) progress.hidden = true;
      });
      xhr.addEventListener("error", () => {
        if (note) note.textContent = "Network error; upload failed";
        if (progress) progress.hidden = true;
      });
      xhr.send(data);
    });
  }

  window.TrovePlayer = { loadItem, toggle, state };
})();
