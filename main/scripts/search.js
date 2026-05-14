// search.js

window.searchState = {
  isOpen: false
};

window.initSearch = function () {
  const searchBtn = document.getElementById("searchBtn");
  const searchInput = document.getElementById("searchInput");
  const logo = document.getElementById("logo");
  const searchPanel = document.getElementById("searchPanel");

  if (!searchBtn || !searchInput || !logo || !searchPanel) return;

  window.searchInput = searchInput;
  window.isSearchOpen = window.searchState.isOpen;

  searchBtn.addEventListener("click", () => {
    window.searchState.isOpen = !window.searchState.isOpen;
    window.isSearchOpen = window.searchState.isOpen;

    if (window.searchState.isOpen) {
      logo.style.display = "none";
      searchInput.style.display = "block";
      searchBtn.innerText = "✕";
      searchInput.focus();

      searchPanel.style.display = "block";
      window.renderDefaultSearchPanel();
    } else {
      logo.style.display = "block";
      searchInput.style.display = "none";
      searchBtn.innerText = "🔍";
      searchInput.value = "";

      searchPanel.style.display = "none";
    }
  });

  searchInput.addEventListener("input", () => {
    const value = searchInput.value.trim();

    if (!value) {
      window.renderDefaultSearchPanel();
      return;
    }

    const results = window.searchItems(value);
    window.renderSearchResults(results);
  });
};

window.searchItems = function searchItems(query) {
  const q = query.toLowerCase();

  const allItems =
    typeof window.getFilteredItems === "function"
      ? window.getFilteredItems()
      : [...markersData, ...polygonsData, ...roadsData];

  return allItems.filter((item) => {
    const title = (item.title || "").toLowerCase();
    const desc = (item.description || "").toLowerCase();

    return title.includes(q) || desc.includes(q);
  });
};

window.focusOnItem = function focusOnItem(item) {
  if (item.lat && item.lng) {
    window.map.flyTo([item.lat, item.lng], 14);

    setTimeout(() => {
      window.map.eachLayer((layer) => {
        if (
          layer instanceof L.Marker &&
          layer.getLatLng &&
          layer.getPopup &&
          layer.getPopup()
        ) {
          const latlng = layer.getLatLng();

          const sameLat = Math.abs(latlng.lat - item.lat) < 0.00001;
          const sameLng = Math.abs(latlng.lng - item.lng) < 0.00001;

          if (sameLat && sameLng) {
            layer.openPopup();
          }
        }
      });
    }, 300);
  } else if (item.coords) {
    const bounds = L.latLngBounds(item.coords);
    window.map.fitBounds(bounds);

    setTimeout(() => {
      window.map.eachLayer((layer) => {
        if (layer.getPopup && layer.getPopup()) {
          layer.openPopup();
        }
      });
    }, 300);
  }
};

window.renderDefaultSearchPanel = function renderDefaultSearchPanel() {
  const searchPanel = document.getElementById("searchPanel");

  if (!searchPanel) return;

  if (!window.searchState.isOpen) {
    searchPanel.innerHTML = "";
    return;
  }

  searchPanel.innerHTML = `
    <div class="locationBtn" id="searchGeoBtn">
      ⚙ Моє розташування
    </div>
  `;

  const geoBtn = document.getElementById("searchGeoBtn");

  geoBtn.addEventListener("click", () => {
    if (!navigator.geolocation) {
      alert("Geolocation не підтримується");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;

        if (window.userMarker) {
          window.userMarker.setLatLng([lat, lng]);
        } else {
          window.userMarker = L.circleMarker([lat, lng], {
            radius: 8,
            color: "#4da6ff",
            fillColor: "#4da6ff",
            fillOpacity: 0.9
          }).addTo(window.map);
        }

        window.map.flyTo([lat, lng], 16);
      },
      () => {
        alert("Не вдалося отримати місцезнаходження");
      }
    );
  });
};

window.renderSearchResults = function renderSearchResults(results) {
  const searchPanel = document.getElementById("searchPanel");
  if (!searchPanel) return;

  searchPanel.innerHTML = "";

  if (results.length === 0) {
    window.renderDefaultSearchPanel();
    return;
  }

  const container = document.createElement("div");
  container.className = "searchResults";

  results.slice(0, 9).forEach((item) => {
    const el = document.createElement("div");
    el.className = "searchItem";
    el.innerText = item.title || "Без назви";

    el.addEventListener("click", () => {
      window.focusOnItem(item);
      const searchInput = document.getElementById("searchInput");
      const searchBtn = document.getElementById("searchBtn");
      const logo = document.getElementById("logo");
      const searchPanel = document.getElementById("searchPanel");

      if (searchInput && searchBtn && logo && searchPanel) {
        searchInput.value = "";
        searchInput.style.display = "none";
        searchBtn.innerText = "🔍";
        logo.style.display = "block";
        searchPanel.style.display = "none";

        window.searchState.isOpen = false;
        window.isSearchOpen = false;
      }
    });

    container.appendChild(el);
  });

  searchPanel.appendChild(container);
};