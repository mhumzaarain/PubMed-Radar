import { apiFetch } from "./api.js";

async function loadRadars() {
  const list = document.getElementById("radar-list");
  try {
    const data = await apiFetch("/api/radars/");
    const radars = data.results ?? data;
    if (radars.length === 0) {
      list.textContent = list.dataset.emptyText;
      return;
    }
    for (const radar of radars) {
      const item = document.createElement("li");
      item.textContent = radar.name;
      list.appendChild(item);
    }
  } catch (err) {
    list.textContent = "Could not load radars.";
    console.error(err);
  }
}

loadRadars();
