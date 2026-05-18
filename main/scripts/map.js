// =========================
// 1. INIT MAP
// =========================

// Межі Києва
const kyivBounds = L.latLngBounds(
  [50.35, 30.30], // South-West
  [50.60, 30.75]  // North-East
);

window.map = L.map('map', {
  maxZoom: 18,
  maxBounds: kyivBounds,
  maxBoundsViscosity: 1.0,
  worldCopyJump: false
});

const map = window.map;

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap',
  noWrap: true
}).addTo(map);

// Автоматично підганяємо карту під межі Києва
map.fitBounds(kyivBounds, {
  padding: [0, 0]
});

// Фіксуємо цей масштаб як мінімальний,
// щоб не можна було віддалитися далі
map.setMinZoom(map.getZoom());

// Додатковий захист від виходу за межі
map.on('drag', function () {
  map.panInsideBounds(kyivBounds, { animate: false });
});



// =========================
// 3. STATE
// =========================
window.markerLayers = {};
window.polygonLayers = {};
window.roadLayers = {};

let selectedDate = normalizeDate(new Date());
window.userMarker = null;
const today = normalizeDate(new Date());



// =========================
// 4. UI ELEMENTS
// =========================
const datePicker = document.getElementById("datePicker");
const prevBtn = document.getElementById("prevDay");
const nextBtn = document.getElementById("nextDay");
const dateLabel = document.getElementById("currentDateLabel");
const calendarBtn = document.getElementById("calendarBtn");

// =========================
// 5. HELPERS
// =========================
function normalizeDate(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function formatDate(date) {
  const d = normalizeDate(date);

  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const year = d.getFullYear();

  return `${day}.${month}.${year}`;
}

function formatDateForInput(date) {
  const d = normalizeDate(date);

  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;
}

function isEventVisible(item, selectedDate) {
  const selected = normalizeDate(new Date(selectedDate));

  const itemDate = item.date ? normalizeDate(new Date(item.date)) : null;
  const start = item.startDate ? normalizeDate(new Date(item.startDate)) : null;
  const end = item.endDate ? normalizeDate(new Date(item.endDate)) : null;

  if (selected.getTime() === today.getTime()) {

    if (itemDate) {
      if (itemDate >= today) return true;

      const diff = (today - itemDate) / (1000 * 60 * 60 * 24);
      return diff <= 7;
    }

    if (start) {
      if (end) {
        return selected <= end;
      }

      const extendedEnd = new Date(start);
      extendedEnd.setDate(extendedEnd.getDate() + 7);

      return extendedEnd >= today;
    }

    return true;
  }

  if (itemDate) {
    return itemDate.getTime() === selected.getTime();
  }

  if (start && end) {
    return selected >= start && selected <= end;
  }

  return false;
}

window.getFilteredItems = function getFilteredItems() {
  const result = [];

  const pushIfVisible = (item) => {
    if (!isEventVisible(item, selectedDate)) return;

    if (typeof window.isItemInSelectedRaions === "function") {
      if (!window.isItemInSelectedRaions(item)) return;
    }

    const categoryKey = item.category || "default";

    const filterInput = document.querySelector(`#filters input[value="${categoryKey}"]`);
    if (filterInput && !filterInput.checked) return;

    result.push(item);
  };

  markersData.forEach(pushIfVisible);
  polygonsData.forEach(pushIfVisible);
  roadsData.forEach(pushIfVisible);

  return result;
};


// =========================
// 6. RENDER
// =========================
function shouldRenderItem(item) {
  if (!isEventVisible(item, selectedDate)) return false;

  if (typeof window.isItemInSelectedRaions === "function") {
    if (!window.isItemInSelectedRaions(item)) return false;
  }

  const categoryKey = item.category || "default";
  const filterInput = document.querySelector(`#filters input[value="${categoryKey}"]`);

  if (filterInput && !filterInput.checked) return false;

  return true;
}

function clearLayerGroups(layerGroups) {
  Object.values(layerGroups).forEach((layer) => {
    layer.clearLayers();
    map.removeLayer(layer);
  });
}

function renderMarkers() {
  markersData.forEach((item) => {
    if (!shouldRenderItem(item)) return;

    const categoryKey = item.category || "default";

    if (!markerLayers[categoryKey]) {
      markerLayers[categoryKey] = L.layerGroup();
    }

    markerLayers[categoryKey].addTo(map);

    const marker = L.marker([item.lat, item.lng], {
      icon: createMarkerIcon(item)
    }).bindPopup(createPopupContent(item));

    markerLayers[categoryKey].addLayer(marker);
  });
}

function renderPolygons() {
  polygonsData.forEach((poly) => {
    if (!shouldRenderItem(poly)) return;

    const categoryKey = poly.category || "default";

    if (!polygonLayers[categoryKey]) {
      polygonLayers[categoryKey] = L.layerGroup();
    }

    polygonLayers[categoryKey].addTo(map);

    const polygon = L.polygon(poly.coords, {
      color: "gray",
      fillOpacity: 0.4
    }).bindPopup(createPopupContent(poly));

    polygonLayers[categoryKey].addLayer(polygon);
  });
}

function renderRoads() {
  roadsData.forEach((road) => {
    if (!shouldRenderItem(road)) return;

    const categoryKey = road.category || "default";

    if (!roadLayers[categoryKey]) {
      roadLayers[categoryKey] = L.layerGroup();
    }

    roadLayers[categoryKey].addTo(map);

    const polyline = L.polyline(road.coords, {
      color: "gray",
      weight: 5
    }).bindPopup(createPopupContent(road));

    roadLayers[categoryKey].addLayer(polyline);
  });
}

window.refreshMap = function refreshMap() {
  clearLayerGroups(markerLayers);
  clearLayerGroups(polygonLayers);
  clearLayerGroups(roadLayers);

  renderMarkers();
  renderPolygons();
  renderRoads();

  if (typeof window.applyCurrentFilters === "function") {
    window.applyCurrentFilters();
  }
};





// =========================
// 7. EVENTS
// =========================

prevBtn.addEventListener("click", () => {
  const prevDate = normalizeDate(new Date(selectedDate));
  prevDate.setDate(prevDate.getDate() - 1);

  selectedDate = prevDate;

  datePicker.value = formatDateForInput(selectedDate);
  updateDateUI();
  refreshMap();
});

nextBtn.addEventListener("click", () => {
  const nextDate = normalizeDate(new Date(selectedDate));
  nextDate.setDate(nextDate.getDate() + 1);

  if (nextDate.getTime() > today.getTime()) return;

  selectedDate = nextDate;

  datePicker.value = formatDateForInput(selectedDate);
  updateDateUI();
  refreshMap();
});

datePicker.addEventListener("change", function() {

  if (!this.value) {
    selectedDate = normalizeDate(new Date());
  } else {
    selectedDate = normalizeDate(new Date(this.value));
  }

  datePicker.value = formatDateForInput(selectedDate);

  updateDateUI();
  refreshMap();
});

calendarBtn.addEventListener("click", () => {
  datePicker.style.pointerEvents = "auto";
  datePicker.style.opacity = "1";

  datePicker.showPicker();

  setTimeout(() => {
    datePicker.style.pointerEvents = "none";
    datePicker.style.opacity = "0";
  }, 100);
});



// =========================
// XX. XXXXX
// =========================
function updateDateUI() {
  dateLabel.innerText = formatDate(selectedDate);

  nextBtn.disabled = selectedDate.getTime() === today.getTime();
}

function createPopupContent(item) {
  return `
    <div style="max-width:200px">
      <b>${item.title || "Без назви"}</b><br><br>

      ${item.image ? `<img src="${item.image}" style="width:100%; border-radius:6px;"><br><br>` : ""}

      <div>${item.description || ""}</div><br>

      ${item.date ? `<b>Дата:</b> ${item.date}<br>` : ""}
      ${item.startDate ? `<b>Початок:</b> ${item.startDate}<br>` : ""}
      ${item.endDate ? `<b>Кінець:</b> ${item.endDate}<br>` : ""}
    </div>
  `;
}

function createMarkerIcon(item) {
  return L.divIcon({
    className: '',
    html: `
      <div style="
        width:30px;
        height:30px;
        background:#FF3B30;
        border-radius:50% 50% 50% 0;
        transform: rotate(-45deg);
        position: relative;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
      ">
        <div style="
          width:12px;
          height:12px;
          background:white;
          border-radius:50%;
          position:absolute;
          top:9px;
          left:9px;
          transform: rotate(45deg);
        "></div>
      </div>
    `,

    iconSize: [30, 30],
    iconAnchor: [15, 30],
    popupAnchor: [0, -30]
  });
}




// =========================
// 9. INIT APP
// =========================
datePicker.max = formatDateForInput(today);
datePicker.value = formatDateForInput(selectedDate);

updateDateUI();
window.refreshMap();

if (window.initFilters) {
  window.initFilters();
}

if (window.initSearch) {
  window.initSearch();
}

window.loadAlerts();