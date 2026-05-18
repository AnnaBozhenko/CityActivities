window.filtersState = {
  raions: [],
  raionsGeoJson: null,
  selectedRaions: new Set()
};

window.metroLayersState = {
  metroLinesLayer: null,
  metroStationsLayer: null,
  isMetroLoaded: false
};

window.tomtomLayersState = {
  trafficFlowLayer: null,
  incidentsLayer: null,
  isTrafficFlowLoaded: false,
  isIncidentsLoaded: false
};




window.applyCurrentFilters = function () {
  const inputs = document.querySelectorAll("#filters input");

  // 1. Фільтри для міток / полігонів / доріг
  inputs.forEach((input) => {
    const type = input.value;
    const checked = input.checked;

    if (window.markerLayers && window.markerLayers[type]) {
      checked
        ? window.map.addLayer(window.markerLayers[type])
        : window.map.removeLayer(window.markerLayers[type]);
    }

    if (window.polygonLayers && window.polygonLayers[type]) {
      checked
        ? window.map.addLayer(window.polygonLayers[type])
        : window.map.removeLayer(window.polygonLayers[type]);
    }

    if (window.roadLayers && window.roadLayers[type]) {
      checked
        ? window.map.addLayer(window.roadLayers[type])
        : window.map.removeLayer(window.roadLayers[type]);
    }
  });

  // 2. Метро (повністю окремо від районів)
  const metroLinesInput = document.querySelector('input[value="metroLines"]');
  const metroStationsInput = document.querySelector('input[value="metroStations"]');

  const metroLinesLayer = window.metroLayersState?.metroLinesLayer;
  const metroStationsLayer = window.metroLayersState?.metroStationsLayer;

  if (metroLinesInput && metroLinesLayer) {
    if (metroLinesInput.checked) {
      window.map.addLayer(metroLinesLayer);
    } else {
      window.map.removeLayer(metroLinesLayer);
    }
  }

  if (metroStationsInput && metroStationsLayer) {
    if (metroStationsInput.checked) {
      window.map.addLayer(metroStationsLayer);
    } else {
      window.map.removeLayer(metroStationsLayer);
    }
  }

  // 3. TomTom traffic flow та інциденти
  const trafficFlowInput = document.querySelector('input[value="tomtomTrafficFlow"]');
  const tomtomIncidentsInput = document.querySelector('input[value="tomtomIncidents"]');

  const trafficFlowLayer = window.tomtomLayersState?.trafficFlowLayer;
  const incidentsLayer = window.tomtomLayersState?.incidentsLayer;

  if (trafficFlowInput && trafficFlowLayer) {
    trafficFlowInput.checked
      ? window.map.addLayer(trafficFlowLayer)
      : window.map.removeLayer(trafficFlowLayer);
  }

  if (tomtomIncidentsInput && incidentsLayer) {
    tomtomIncidentsInput.checked
      ? window.map.addLayer(incidentsLayer)
      : window.map.removeLayer(incidentsLayer);
  }
};

window.renderSelectedRaionsTags = function () {
  const panel = document.getElementById("selectedRaionsPanel");
  const tags = document.getElementById("selectedRaionsTags");

  if (!panel || !tags) return;

  const selected = [...window.filtersState.selectedRaions];

  if (selected.length === 0) {
    panel.style.display = "none";
    tags.innerHTML = "";
    return;
  }

  panel.style.display = "block";

  tags.innerHTML = selected
    .map((name) => {
      return `
        <span class="selectedRaionTag">
          ${name}
          <button
            type="button"
            class="selectedRaionRemove"
            data-raion-remove="${name}"
          >
            ×
          </button>
        </span>
      `;
    })
    .join("");

  tags.querySelectorAll("[data-raion-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const raionName = btn.dataset.raionRemove;

      window.filtersState.selectedRaions.delete(raionName);

      const checkbox = document.querySelector(
        `#raionsList input[data-raion-name="${CSS.escape(raionName)}"]`
      );

      if (checkbox) {
        checkbox.checked = false;
      }

      window.renderSelectedRaionsTags();
    });
  });
};

window.renderRaionsList = function (searchValue = "") {
  const list = document.getElementById("raionsList");
  if (!list) return;

  const query = searchValue.trim().toLowerCase();

  const filteredRaions = window.filtersState.raions.filter((name) =>
    name.toLowerCase().includes(query)
  );

  list.innerHTML = filteredRaions
    .map((name) => {
      const checked = window.filtersState.selectedRaions.has(name) ? "checked" : "";

      return `
        <div class="multiSelectItem">
          <input
            type="checkbox"
            ${checked}
            data-raion-name="${name}"
            id="raion-${name}"
          >
          <label for="raion-${name}">${name}</label>
        </div>
      `;
    })
    .join("");

  list.querySelectorAll("input[data-raion-name]").forEach((input) => {
    input.addEventListener("change", () => {
      const raionName = input.dataset.raionName;

      if (input.checked) {
        window.filtersState.selectedRaions.add(raionName);
      } else {
        window.filtersState.selectedRaions.delete(raionName);
      }

      window.renderSelectedRaionsTags();
    });
  });
};

window.loadRaions = async function () {
  try {
    const response = await fetch("data/kyiv_raions.geojson");
    const data = await response.json();

    window.filtersState.raionsGeoJson = data;

    const names = (data.features || [])
      .map((feature) => feature?.properties?.NAME)
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "uk"));

    window.filtersState.raions = names;

    window.renderRaionsList();
    window.renderSelectedRaionsTags();
  } catch (error) {
    console.error("Помилка завантаження районів:", error);
  }
};

window.initRaionsSearch = function () {
  const searchInput = document.getElementById("raionsSearchInput");
  if (!searchInput) return;

  searchInput.addEventListener("input", () => {
    window.renderRaionsList(searchInput.value);
  });
};

window.initRaionsClear = function () {
  const clearBtn = document.getElementById("clearRaionsBtn");
  if (!clearBtn) return;

  clearBtn.addEventListener("click", () => {
    window.filtersState.selectedRaions.clear();

    const searchInput = document.getElementById("raionsSearchInput");
    const currentSearch = searchInput ? searchInput.value : "";

    window.renderRaionsList(currentSearch);
    window.renderSelectedRaionsTags();
  });
};

window.isPointInRing = function (lng, lat, ring) {
  let inside = false;

  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];

    const intersects =
      ((yi > lat) !== (yj > lat)) &&
      (lng < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi);

    if (intersects) {
      inside = !inside;
    }
  }

  return inside;
};

window.isPointInPolygonCoords = function (lng, lat, polygonCoords) {
  if (!polygonCoords || polygonCoords.length === 0) return false;

  const outerRing = polygonCoords[0];
  if (!window.isPointInRing(lng, lat, outerRing)) return false;

  for (let i = 1; i < polygonCoords.length; i++) {
    if (window.isPointInRing(lng, lat, polygonCoords[i])) {
      return false;
    }
  }

  return true;
};

window.isPointInFeatureGeometry = function (lng, lat, geometry) {
  if (!geometry) return false;

  if (geometry.type === "Polygon") {
    return window.isPointInPolygonCoords(lng, lat, geometry.coordinates);
  }

  if (geometry.type === "MultiPolygon") {
    return geometry.coordinates.some((polygonCoords) =>
      window.isPointInPolygonCoords(lng, lat, polygonCoords)
    );
  }

  return false;
};

window.isAnyPointInSelectedRaions = function (points) {
  const selectedRaions = window.filtersState.selectedRaions;

  if (!selectedRaions || selectedRaions.size === 0) {
    return true;
  }

  const geoJson = window.filtersState.raionsGeoJson;
  if (!geoJson || !Array.isArray(geoJson.features)) {
    return true;
  }

  if (!Array.isArray(points) || points.length === 0) {
    return false;
  }

  for (const point of points) {
    const lng = point.lng;
    const lat = point.lat;

    if (typeof lng !== "number" || typeof lat !== "number") {
      continue;
    }

    for (const feature of geoJson.features) {
      const raionName = feature?.properties?.NAME;

      if (!selectedRaions.has(raionName)) continue;

      if (window.isPointInFeatureGeometry(lng, lat, feature.geometry)) {
        return true;
      }
    }
  }

  return false;
};

window.isItemInSelectedRaions = function (item) {
  if (!item) return false;

  if (typeof item.lat === "number" && typeof item.lng === "number") {
    return window.isAnyPointInSelectedRaions([
      { lat: item.lat, lng: item.lng }
    ]);
  }

  if (Array.isArray(item.coords) && item.coords.length > 0) {
    const points = item.coords.map((coord) => ({
      lat: coord[0],
      lng: coord[1]
    }));

    return window.isAnyPointInSelectedRaions(points);
  }

  return false;
};

window.initFilters = async function () {
  const applyBtn = document.getElementById("applyFiltersBtn");

  await window.loadRaions();
  await window.loadMetroLayers();
  await window.initTomTomLayers();

  window.initRaionsSearch();
  window.initRaionsClear();

  if (!applyBtn) return;

  applyBtn.addEventListener("click", () => {
    if (typeof window.refreshMap === "function") {
      window.refreshMap();
    }

    window.applyCurrentFilters();
  });
};




window.loadMetroLayers = async function () {
  if (window.metroLayersState.isMetroLoaded) return;

  try {
    const [linesRes, stationsRes] = await Promise.all([
      fetch("data/kyiv_subway.geojson"),
      fetch("data/kyiv_subway_stations.geojson")
    ]);

    const [linesData, stationsData] = await Promise.all([
      linesRes.json(),
      stationsRes.json()
    ]);

    window.metroLayersState.metroLinesLayer = L.geoJson(linesData, {
      style: function (feature) {
        const lineColor = feature.properties.line_color || "#888";

        return {
          color: lineColor,
          weight: 4,
          opacity: 1
        };
      }
    });

    window.metroLayersState.metroStationsLayer = L.geoJson(stationsData, {
      pointToLayer: function (feature, latlng) {
        return L.marker(latlng, {
          icon: L.icon({
            iconUrl: "icons/metro_logo.png",
            iconSize: [12, 12],
            iconAnchor: [6, 6],
            popupAnchor: [0, -12]
          })
        });
      },
      onEachFeature: function (feature, layer) {
        const stationName = feature.properties.name || "Станція без назви";
        layer.bindPopup("<b>Станція метро:</b><br>" + stationName);
      }
    });

    window.metroLayersState.isMetroLoaded = true;

    window.applyCurrentFilters();
  } catch (err) {
    console.error("Помилка завантаження метро:", err);
  }
};




const TOMTOM_API_KEY = "";

window.initTomTomTrafficFlow = function () {
  if (window.tomtomLayersState.isTrafficFlowLoaded) return;

  window.tomtomLayersState.trafficFlowLayer = L.tileLayer(
    `https://api.tomtom.com/traffic/map/4/tile/flow/relative/{z}/{x}/{y}.png?key=${encodeURIComponent(TOMTOM_API_KEY)}&thickness=6&tileSize=256`,
    {
      tileSize: 256,
      opacity: 0.85,
      attribution: "&copy; TomTom Traffic"
    }
  );

  window.tomtomLayersState.isTrafficFlowLoaded = true;
};

window.getTomTomDelayLabel = function (magnitude) {
  const labels = {
    0: "Unknown",
    1: "Minor",
    2: "Moderate",
    3: "Major",
    4: "Severe"
  };

  return labels[magnitude] || "Unknown";
};

window.loadTomTomIncidents = async function () {
  if (!window.tomtomLayersState.incidentsLayer) {
    window.tomtomLayersState.incidentsLayer = L.layerGroup();
  }

  const incidentsLayer = window.tomtomLayersState.incidentsLayer;

  const bounds = window.map.getBounds();

  const bbox = [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth()
  ].join(",");

  const fields = encodeURIComponent(
    "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code,iconCategory},from,to,startTime,endTime,length,delay,roadNumbers,timeValidity}}}"
  );

  const url =
    `https://api.tomtom.com/traffic/services/5/incidentDetails` +
    `?key=${encodeURIComponent(TOMTOM_API_KEY)}` +
    `&bbox=${encodeURIComponent(bbox)}` +
    `&fields=${fields}` +
    `&timeValidityFilter=present`;

  try {
    const response = await fetch(url);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Incident Details HTTP ${response.status}: ${errorText}`);
    }

    const data = await response.json();
    const incidents = data.incidents || [];
    incidentsLayer.clearLayers();

    incidents.forEach((incident) => {
      const coords = incident.geometry?.coordinates || [];
      const props = incident.properties || {};
      const firstEvent = props.events?.[0];
      const description = firstEvent?.description || "";

      if (coords.length < 2) return;

      const delayLabel = window.getTomTomDelayLabel(props.magnitudeOfDelay);
      const latlngs = coords.map(([lng, lat]) => [lat, lng]);

      L.polyline(latlngs, {
        color: "#111827",
        weight: 5,
        opacity: 0.9
      }).addTo(incidentsLayer);

      const startPoint = latlngs[0];
      const endPoint = latlngs[latlngs.length - 1];

      L.circleMarker(startPoint, {
        radius: 4,
        color: "#111827",
        fillColor: "#111827",
        fillOpacity: 0.95,
        weight: 2
      })
        .bindPopup(`
          <b>Road incident</b><br>
          Description: ${description || "-"}<br>
          Delay level: ${delayLabel}<br>
          From: ${props.from || "-"}<br>
          To: ${props.to || "-"}<br>
          Length: ${props.length ?? "-"} m<br>
          Delay: ${props.delay ?? "-"} sec
        `)
        .addTo(incidentsLayer);

      L.circleMarker(endPoint, {
        radius: 4,
        color: "#111827",
        fillColor: "#111827",
        fillOpacity: 0.95,
        weight: 2
      })
        .bindPopup(`
          <b>Road incident</b><br>
          Description: ${description || "-"}<br>
          Delay level: ${delayLabel}<br>
          From: ${props.from || "-"}<br>
          To: ${props.to || "-"}<br>
          Length: ${props.length ?? "-"} m<br>
          Delay: ${props.delay ?? "-"} sec
        `)
        .addTo(incidentsLayer);
    });

    window.tomtomLayersState.isIncidentsLoaded = true;
    window.applyCurrentFilters();
  } catch (error) {
    console.error("TomTom incidents error:", error);
  }
};

window.showTrafficPopup = async function (latlng) {
  const trafficFlowInput = document.querySelector('input[value="tomtomTrafficFlow"]');

  if (!trafficFlowInput || !trafficFlowInput.checked) return;

  const trafficFlowLayer = window.tomtomLayersState?.trafficFlowLayer;

  if (!trafficFlowLayer || !window.map.hasLayer(trafficFlowLayer)) return;

  const popup = L.popup()
    .setLatLng(latlng)
    .setContent("Завантаження traffic flow...")
    .openOn(window.map);

  const zoom = window.map.getZoom();

  const url =
    `https://api.tomtom.com/traffic/services/4/flowSegmentData/relative/${zoom}/json` +
    `?key=${encodeURIComponent(TOMTOM_API_KEY)}` +
    `&point=${latlng.lat},${latlng.lng}` +
    `&unit=kmph`;

  try {
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Flow Segment HTTP ${response.status}`);
    }

    const data = await response.json();
    const flow = data.flowSegmentData;

    if (!flow) {
      popup.setContent("Немає traffic flow даних для цієї точки.");
      return;
    }

    const currentSpeed = flow.currentSpeed;
    const freeFlowSpeed = flow.freeFlowSpeed;
    const ratio = freeFlowSpeed ? currentSpeed / freeFlowSpeed : null;
    const trafficPercent = ratio ? Math.round(ratio * 100) : null;

    popup.setContent(`
      <b>Traffic Flow</b><br>
      Поточна швидкість: ${currentSpeed} км/год<br>
      Нормальна швидкість: ${freeFlowSpeed} км/год<br>
      Рівень руху: ${trafficPercent ?? "-"}%
    `);

  } catch (error) {
    console.error("TomTom traffic flow popup error:", error);
    popup.setContent("Не вдалося завантажити traffic flow дані.");
  }
};

window.initTomTomLayers = async function () {
  window.initTomTomTrafficFlow();

  await window.loadTomTomIncidents();

  window.map.on("moveend", async () => {
    await window.loadTomTomIncidents();
  });

  window.map.on("click", function (event) {
    if (typeof window.showTrafficPopup === "function") {
      window.showTrafficPopup(event.latlng);
    }
  });
};

window.updateTomTomData = async function () {
  await window.loadTomTomIncidents();
};