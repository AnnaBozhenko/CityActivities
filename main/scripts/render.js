// render.js

window.renderStatusState = {
  intervalSeconds: 30,
  secondsLeft: 30,
  timerId: null,
  autoRenderId: null,
  isRendering: false,
  lastUpdatedAt: null
};

window.formatRenderDateTime = function (date) {
  if (!(date instanceof Date)) return "—";

  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();

  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");

  return `${day}.${month}.${year} ${hours}:${minutes}:${seconds}`;
};

window.updateRenderStatusUI = function () {
  const lastUpdateTimeEl = document.getElementById("lastUpdateTime");
  const countdownEl = document.getElementById("nextUpdateCountdown");
  const statusDotEl = document.getElementById("statusDot");
  const refreshIconEl = document.getElementById("refreshIcon");

  if (lastUpdateTimeEl) {
    lastUpdateTimeEl.textContent = window.renderStatusState.lastUpdatedAt
      ? window.formatRenderDateTime(window.renderStatusState.lastUpdatedAt)
      : "—";
  }

  if (countdownEl) {
    countdownEl.textContent = window.renderStatusState.secondsLeft;
  }

  if (statusDotEl) {
    statusDotEl.classList.toggle("is-rendering", window.renderStatusState.isRendering);
  }

  if (refreshIconEl) {
    refreshIconEl.classList.toggle("is-rendering", window.renderStatusState.isRendering);
    refreshIconEl.style.cursor = "pointer";
    refreshIconEl.title = "Оновити зараз";
  }
};

window.rerenderSearchUI = function () {
  if (!window.isSearchOpen) return;
  if (!window.searchInput) return;

  const value = window.searchInput.value.trim();

  if (!value) {
    if (typeof window.renderDefaultSearchPanel === "function") {
      window.renderDefaultSearchPanel();
    }
    return;
  }

  if (
    typeof window.searchItems === "function" &&
    typeof window.renderSearchResults === "function"
  ) {
    const results = window.searchItems(value);
    window.renderSearchResults(results);
  }
};

window.resetRenderCountdown = function () {
  window.renderStatusState.secondsLeft = window.renderStatusState.intervalSeconds;
  window.updateRenderStatusUI();
};

window.startRenderCountdown = function () {
  if (window.renderStatusState.timerId) {
    clearInterval(window.renderStatusState.timerId);
  }

  window.resetRenderCountdown();

  window.renderStatusState.timerId = setInterval(() => {
    if (window.renderStatusState.isRendering) return;

    window.renderStatusState.secondsLeft -= 1;

    if (window.renderStatusState.secondsLeft <= 0) {
      window.renderStatusState.secondsLeft = 0;
    }

    window.updateRenderStatusUI();
  }, 1000);
};

window.rerenderApp = async function () {
  if (window.renderStatusState.isRendering) return;

  try {
    window.renderStatusState.isRendering = true;
    window.updateRenderStatusUI();

    // 1. Оновлення карти
    if (typeof window.refreshMap === "function") {
      window.refreshMap();
    }

    // 2. Повторне застосування фільтрів
    window.applyCurrentFilters();

    // 3. Відновлення пошукової панелі/результатів
    window.rerenderSearchUI();

    // 4. Оновлення блоку тривоги
    if (typeof window.loadAlerts === "function") {
      await window.loadAlerts();
    }

    // 5. Статус часу оновлення
    window.renderStatusState.lastUpdatedAt = new Date();
    window.resetRenderCountdown();
  } catch (error) {
    console.error("Render error:", error);
  } finally {
    window.renderStatusState.isRendering = false;
    window.updateRenderStatusUI();
  }
};

window.startAutoRender = function () {
  if (window.renderStatusState.autoRenderId) {
    clearInterval(window.renderStatusState.autoRenderId);
  }

  window.startRenderCountdown();

  window.renderStatusState.autoRenderId = setInterval(async () => {
    await window.rerenderApp();
  }, window.renderStatusState.intervalSeconds * 1000);
};

window.initRenderStatus = function () {
  const refreshIcon = document.getElementById("refreshIcon");

  if (refreshIcon) {
    refreshIcon.addEventListener("click", async () => {
      await window.rerenderApp();
    });
  }

  window.renderStatusState.lastUpdatedAt = new Date();
  window.updateRenderStatusUI();
  window.startAutoRender();
};

document.addEventListener("DOMContentLoaded", () => {
  window.initRenderStatus();
});