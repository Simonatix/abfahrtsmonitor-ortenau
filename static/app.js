const searchInput = document.getElementById("stop-search");
const suggestionsBox = document.getElementById("suggestions");
const errorBox = document.getElementById("error");
const board = document.getElementById("board");
const stopName = document.getElementById("stop-name");
const tbody = document.getElementById("departures");
const emptyNote = document.getElementById("empty");
const updatedNote = document.getElementById("updated");
const filtersBox = document.getElementById("filters");
const refreshBtn = document.getElementById("refresh");

let currentStop = null;
let currentFilter = "all";
let refreshTimer = null;

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

async function api(path) {
  const response = await fetch(path);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

let debounceTimer = null;
searchInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  const q = searchInput.value.trim();
  if (q.length < 2) {
    suggestionsBox.hidden = true;
    return;
  }
  debounceTimer = setTimeout(() => searchStops(q), 250);
});

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    clearTimeout(debounceTimer);
    searchStops(searchInput.value.trim());
  }
});

document.addEventListener("click", (event) => {
  if (event.target === searchInput || suggestionsBox.contains(event.target)) return;
  suggestionsBox.hidden = true;
});

async function searchStops(q) {
  showError("");
  try {
    const data = await api(`/api/stops?q=${encodeURIComponent(q)}`);
    renderSuggestions(data.stops);
  } catch (err) {
    showError(`Haltestellensuche fehlgeschlagen: ${err.message}`);
  }
}

function renderSuggestions(stops) {
  suggestionsBox.innerHTML = "";
  if (!stops.length) {
    suggestionsBox.innerHTML = '<div class="suggestion empty">Keine Haltestelle im Ortenaukreis gefunden.</div>';
    suggestionsBox.hidden = false;
    return;
  }
  for (const stop of stops) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "suggestion";
    item.innerHTML = `<strong>${escapeHtml(stop.name)}</strong><span>${escapeHtml(stop.place)}</span>`;
    item.addEventListener("click", () => selectStop(stop));
    suggestionsBox.appendChild(item);
  }
  suggestionsBox.hidden = false;
}

function selectStop(stop) {
  currentStop = stop;
  suggestionsBox.hidden = true;
  searchInput.value = stop.name;
  stopName.textContent = stop.name;
  board.hidden = false;
  loadDepartures();
}

document.querySelectorAll(".quick button").forEach((btn) => {
  btn.addEventListener("click", () => {
    searchInput.value = btn.dataset.q;
    searchStops(btn.dataset.q);
  });
});

filtersBox.addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (!chip) return;
  currentFilter = chip.dataset.filter;
  filtersBox.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === chip));
  renderDepartures();
});

refreshBtn.addEventListener("click", loadDepartures);

async function loadDepartures() {
  if (!currentStop) return;
  showError("");
  try {
    const data = await api(`/api/departures?stop=${encodeURIComponent(currentStop.gid)}`);
    currentStop.departures = data.departures;
    currentStop.serverTime = data.serverTime;
    stopName.textContent = data.stop.name || currentStop.name;
    updatedNote.textContent = data.serverTime
      ? `Stand: ${data.serverTime.replace("T", " ").slice(0, 16)} Uhr`
      : "";
    renderDepartures();
  } catch (err) {
    showError(`Abfahrten konnten nicht geladen werden: ${err.message}`);
  }
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(loadDepartures, 30000);
}

function renderDepartures() {
  if (!currentStop || !currentStop.departures) return;
  const deps = currentStop.departures.filter(
    (d) => currentFilter === "all" || d.kind === currentFilter
  );
  tbody.innerHTML = "";
  emptyNote.hidden = deps.length > 0;
  for (const dep of deps) {
    const row = document.createElement("tr");
    if (dep.cancelled) row.classList.add("cancelled");

    const timeCell = document.createElement("td");
    timeCell.className = "time";
    let sub = "";
    if (dep.cancelled) {
      sub = '<span class="fall">fällt aus</span>';
    } else if (dep.realtime && dep.real !== dep.planned) {
      sub = `Prognose <strong>${dep.real}</strong>`;
      if (dep.delay > 0) sub += ` <span class="delay">+${dep.delay} min</span>`;
    } else if (dep.realtime) {
      sub = '<span class="ontime">pünktlich</span>';
    }
    timeCell.innerHTML = `<strong>${dep.planned}</strong><br><span class="sub">${sub}</span>`;

    const lineCell = document.createElement("td");
    lineCell.innerHTML = `<span class="badge kind-${dep.kind}">${escapeHtml(dep.line)}</span>`;
    if (dep.product) lineCell.title = dep.product;

    const dirCell = document.createElement("td");
    dirCell.textContent = dep.direction;
    if (dep.hints.length) dirCell.title = dep.hints.join("\n");

    const platformCell = document.createElement("td");
    platformCell.className = "platform";
    platformCell.textContent = dep.platform || "–";

    const statusCell = document.createElement("td");
    statusCell.className = "status";
    if (dep.cancelled) {
      statusCell.textContent = "ausgefallen";
    } else if (dep.countdown !== null && dep.countdown >= 0) {
      statusCell.textContent = dep.countdown === 0 ? "sofort" : `in ${dep.countdown} min`;
    } else {
      statusCell.textContent = dep.realtime ? "Echtzeit" : "Soll";
    }

    row.append(timeCell, lineCell, dirCell, platformCell, statusCell);
    tbody.appendChild(row);
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
