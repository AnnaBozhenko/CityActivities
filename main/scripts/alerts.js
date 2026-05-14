// alerts.js

window.alertsState = {
  isAirAlert: false,
};

window.renderAlerts = function () {
  function formatAlertDateTime(dateStr) {
    if (!dateStr) return "";

    const date = new Date(dateStr.replace(" ", "T"));

    const day = String(date.getDate()).padStart(2, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const year = date.getFullYear();

    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");

    return `${day}.${month}.${year} ${hours}:${minutes}:${seconds}`;
  }

  const dot = document.getElementById("alertDot");
  const text = document.getElementById("alertText");

  if (!dot || !text) return;

  if (window.alertsState.isAirAlert) {
    dot.classList.add("is-alert");

    const formattedTime = formatAlertDateTime(window.alertsState.changedAt);

    text.innerHTML = formattedTime
      ? `Повітряна тривога<br>${formattedTime}`
      : "Повітряна тривога";

  } else {
    dot.classList.remove("is-alert");
    text.textContent = "Тривоги немає";
  }
};

window.loadAlerts = async function () {
  try {
    const targetUrl = `https://ubilling.net.ua/aerialalerts/?t=${Date.now()}`;
    const proxyUrl = `https://corsproxy.io/?${encodeURIComponent(targetUrl)}`;

    const res = await fetch(proxyUrl);
    const data = await res.json();
    const kyiv = data?.states?.["м. Київ"];

    if (!kyiv) {
      console.warn('У даних немає ключа "м. Київ"');
      return;
    }

    window.alertsState.isAirAlert = kyiv.alertnow === true;
    window.alertsState.changedAt = kyiv.changed || null;

    window.renderAlerts();
  } catch (e) {
    console.error("Alert API error:", e);
  }
};