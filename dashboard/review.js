/* Render evidence as text nodes. Imagery metadata must never become markup. */
const byId = (id) => document.getElementById(id);
const queue = byId("queue");
const detail = byId("detail");
const status = byId("status");
let map, generation = 0, items = [];
const changedColor = "#fe806f";
const newColor = "#51dfc3";

if (window.maplibregl) {
  try {
    map = new maplibregl.Map({
      container: "map", center: [-87.633, 41.8835], zoom: 14,
      style: {version: 8, sources: {osm: {type: "raster", tileSize: 256,
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}},
        layers: [{id: "base", type: "raster", source: "osm"}]}
    });
    map.addControl(new maplibregl.NavigationControl());
    map.on("load", () => {
      map.addSource("candidates", {type: "geojson", data: {type: "FeatureCollection", features: items}});
      map.addLayer({id: "candidates", source: "candidates", type: "circle", paint: {
        "circle-radius": 7, "circle-color": ["match", ["get", "type"], "changed", changedColor, newColor],
        "circle-stroke-width": 2, "circle-stroke-color": "#10233a"
      }});
      map.on("click", "candidates", (event) => show(event.features[0].properties.id));
      map.on("mouseenter", "candidates", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "candidates", () => { map.getCanvas().style.cursor = ""; });
    });
  } catch {
    byId("map").textContent = "Map unavailable. Use the ranked review queue.";
  }
}
if (!map) byId("map").textContent = "Map unavailable. Use the ranked review queue.";

function line(parent, text, tag = "p") {
  const node = document.createElement(tag);
  node.textContent = text;
  parent.append(node);
  return node;
}

async function fetchData(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function description(p) {
  if (p.kind === "speed_limit" && p.type === "changed") return `Speed limit mismatch · ${p.value} vs ${p.mapped_value} mph`;
  return `${p.type === "new" ? "New" : "Changed"} · ${p.kind.replaceAll("_", " ")}`;
}

async function load() {
  const ticket = ++generation;
  const query = new URLSearchParams({min_conf: byId("confidence").value});
  if (byId("type").value) query.set("type", byId("type").value);
  byId("minimum").textContent = `${Math.round(Number(byId("confidence").value) * 100)}%`;
  try {
    const data = await fetchData(`/changes?${query}`);
    if (ticket !== generation) return;
    items = data.features;
    byId("mode").textContent = data.mode === "demo" ? "Synthetic demo" : "Live review";
    status.textContent = `${items.length} ranked candidates`;
    queue.replaceChildren();
    for (const item of items) {
      const p = item.properties;
      const button = line(queue, `${description(p)} · ${Math.round(p.confidence * 100)}%`, "button");
      button.addEventListener("click", () => {
        if (map) map.easeTo({center: item.geometry.coordinates, zoom: 16});
        show(p.id);
      });
    }
    map?.getSource("candidates")?.setData(data);
  } catch (error) { if (ticket === generation) status.textContent = error.message; }
}

let detailVersion = 0;
async function show(id) {
  const ticket = ++detailVersion;
  detail.hidden = false;
  detail.textContent = "Loading evidence";
  try {
    const p = await fetchData(`/features/${encodeURIComponent(id)}`);
    if (ticket !== detailVersion) return;
    detail.replaceChildren();
    line(detail, description(p), "h2");
    line(detail, `${Math.round(p.confidence * 100)}% confidence · ${p.n_views} views · ${p.residual_m.toFixed(2)} m fit residual`);
    line(detail, `Review: ${p.review}`);
    line(detail, `Evidence IDs: ${p.image_ids.join(", ")}`);
    for (const decision of ["accept", "reject"]) {
      const button = line(detail, decision === "accept" ? "Accept" : "Reject", "button");
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await fetchData(`/changes/${encodeURIComponent(id)}/review`, {method: "POST",
            headers: {"Content-Type": "application/json"}, body: JSON.stringify({decision})});
          if (ticket === detailVersion) show(id);
          load();
        } catch (error) { status.textContent = error.message; button.disabled = false; }
      });
    }
  } catch (error) { if (ticket === detailVersion) detail.textContent = error.message; }
}
byId("type").addEventListener("change", load);
byId("confidence").addEventListener("input", load);
load();
