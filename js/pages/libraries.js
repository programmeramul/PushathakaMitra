// Bengaluru Libraries Page — real imported dataset records from MongoDB.
// Displays verified library locations, contact details, distances, and directions.
// Book holdings remain honestly labelled as unverified.
import { libraryService, bookService } from "../services/api.js";
import { mountChrome, bookCover } from "../ui.js";

const main = document.getElementById("main");
const params = new URLSearchParams(location.search);
const bookId = params.get("book");
const book = bookId ? await bookService.getBook(bookId).catch(() => null) : null;

const POPULAR_AREAS = [
  "All", "Jayanagar", "Indiranagar", "Malleswaram", "Cubbon Park",
  "Koramangala", "Vijayanagar", "HSR Layout", "BTM Layout",
  "Whitefield", "Peenya", "Yelahanka"
];

const state = {
  q: params.get("q") || "",
  area: params.get("area") || "All",
  category: "all",
  hasPhone: false,
  userLocation: null,
  radiusKm: 5,
  page: 1,
  pageSize: 12,
  mode: "search", // "search" or "nearby"
};

main.innerHTML = `
<section class="section" style="margin-bottom:1.5rem">
  <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:1rem">
    <div>
      <h1>Bengaluru Public Libraries</h1>
      <p class="muted" style="margin-top:.4rem">Explore 160 real library records imported from the official Bengaluru KML and public directory datasets.</p>
    </div>
  </div>

  ${book ? `
    <div class="panel soft" style="display:flex;gap:1.2rem;align-items:center;margin-top:1.5rem;padding:16px 20px">
      <div style="width:54px;flex-shrink:0" class="bookcard">${bookCover(book, { wide: true })}</div>
      <div>
        <div style="font-size:.82rem;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--gold)">Finding nearby library for</div>
        <b class="serif" style="font-size:1.1rem;color:var(--green-700)">${book.title}</b>
        <span class="muted" style="font-size:.9rem"> — ${(book.authors || []).join(", ") || "Author unlisted"}</span>
        <div style="font-size:.82rem;color:var(--mute);margin-top:.2rem">
          Note: Individual shelf holdings are unverified. Visit or call the library directly to confirm shelf availability.
        </div>
      </div>
    </div>` : ""}

  <div class="panel" style="margin-top:1.5rem;padding:22px">
    <form id="lib-search-form" style="display:flex;flex-wrap:wrap;gap:.75rem;align-items:center">
      <div style="flex:1;min-width:240px">
        <input type="search" id="lib-q" placeholder="Search by library name, locality, address…" value="${state.q}">
      </div>
      <button type="submit" class="btn">Search</button>
      <button type="button" id="btn-near-me" class="btn secondary" style="display:inline-flex;align-items:center;gap:6px">
        <span>📍</span> Near Me
      </button>
      <button type="button" id="btn-reset" class="btn secondary" style="display:none">Clear Filters</button>
    </form>

    <div style="margin-top:1rem;display:flex;flex-wrap:wrap;gap:1rem;align-items:center;justify-content:space-between">
      <div class="chipbar" id="area-chips">
        ${POPULAR_AREAS.map(a => `
          <button type="button" class="chip" data-area="${a}" aria-pressed="${state.area === a}">${a}</button>
        `).join("")}
      </div>
      <div style="display:flex;gap:1rem;align-items:center;font-size:.88rem">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="chk-phone" ${state.hasPhone ? "checked" : ""}>
          <span>With telephone only</span>
        </label>
        <select id="sel-category" style="width:auto;min-height:36px;height:36px;padding:0 .5rem;font-size:.85rem">
          <option value="all">All Categories</option>
          <option value="Government">Government Libraries</option>
          <option value="Privately Run">Privately Run</option>
          <option value="Miscellaneous">Institutional & Misc</option>
        </select>
      </div>
    </div>

    <div id="near-me-controls" style="display:none;margin-top:1rem;padding-top:.8rem;border-top:1px dashed var(--border);align-items:center;gap:.75rem;font-size:.9rem">
      <span style="font-weight:600;color:var(--green-700)">📍 Using your location</span>
      <label style="display:inline-flex;align-items:center;gap:6px">
        Search radius:
        <select id="sel-radius" style="width:auto;height:32px;min-height:32px;font-size:.85rem;padding:0 .4rem">
          <option value="3">3 km</option>
          <option value="5" selected>5 km</option>
          <option value="10">10 km</option>
          <option value="25">25 km</option>
        </select>
      </label>
      <span id="near-me-status" class="muted" style="font-size:.82rem"></span>
    </div>
  </div>
</section>

<section>
  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:.8rem">
    <p class="muted" id="lib-count">Loading libraries…</p>
  </div>

  <div id="lib-grid" style="display:grid;grid-template-columns:repeat(auto-fill, minmax(320px, 1fr));gap:1.2rem">
    <p class="muted">Loading real library records…</p>
  </div>

  <div id="lib-pagination" style="display:flex;gap:.8rem;justify-content:center;margin:2rem 0">
    <button class="btn secondary small" id="lib-prev" disabled>← Previous</button>
    <span id="lib-page-info" class="muted" style="align-self:center;font-size:.9rem"></span>
    <button class="btn secondary small" id="lib-next" disabled>Next →</button>
  </div>
</section>

<section style="margin-top:3rem;max-width:840px">
  <div class="panel soft">
    <h3 style="font-size:1.1rem;color:var(--green-700);margin-bottom:.5rem">About the Bengaluru Library Dataset</h3>
    <p class="muted" style="font-size:.92rem;line-height:1.5">
      The locations and telephone contacts shown above are imported from official Bengaluru library KML spatial datasets
      and the Karnataka Public Library directory. PustakaMitra AI does not invent or estimate unverified coordinates.
      Individual book lending availability and shelf holdings are unverified.
    </p>
    <div style="margin-top:1rem;display:flex;flex-wrap:wrap;gap:1.2rem;font-size:.9rem">
      <a href="https://karnataka.gov.in/newpage/Public%20Libraries.aspx" target="_blank" rel="noopener noreferrer">Karnataka Public Libraries Directory ↗</a>
      <a href="https://egranthalaya.nic.in/" target="_blank" rel="noopener noreferrer">e-Granthalaya Catalogue ↗</a>
      <a href="https://search.worldcat.org/" target="_blank" rel="noopener noreferrer">WorldCat Catalogue Search ↗</a>
    </div>
  </div>
</section>
`;

const grid = main.querySelector("#lib-grid");
const countEl = main.querySelector("#lib-count");
const prevBtn = main.querySelector("#lib-prev");
const nextBtn = main.querySelector("#lib-next");
const pageInfo = main.querySelector("#lib-page-info");
const resetBtn = main.querySelector("#btn-reset");
const nearMeBox = main.querySelector("#near-me-controls");
const nearMeStatus = main.querySelector("#near-me-status");

function esc(str) {
  if (!str) return "";
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function escUrl(url) {
  return String(url || "").replace(/"/g, "%22");
}

function renderLibraryCard(lib) {
  const card = document.createElement("div");
  card.className = "panel";
  card.style.cssText = "display:flex;flex-direction:column;justify-content:space-between;padding:20px;border-radius:var(--radius-lg);transition:transform .15s, box-shadow .15s;";

  const top = document.createElement("div");

  const badges = document.createElement("div");
  badges.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px;";

  if (lib.category) {
    const catBadge = document.createElement("span");
    catBadge.className = "tag";
    catBadge.textContent = lib.category;
    badges.appendChild(catBadge);
  }

  if (lib.area) {
    const areaBadge = document.createElement("span");
    areaBadge.className = "tag gold";
    areaBadge.textContent = lib.area;
    badges.appendChild(areaBadge);
  }

  if (lib.distance_km !== undefined && lib.distance_km !== null) {
    const distBadge = document.createElement("span");
    distBadge.className = "tag";
    distBadge.style.cssText = "background:var(--green-700);color:#fff;font-weight:600;";
    distBadge.textContent = `📍 ${lib.distance_km} km`;
    badges.appendChild(distBadge);
  }

  top.appendChild(badges);

  const title = document.createElement("h2");
  title.style.cssText = "font-size:1.15rem;color:var(--green-700);margin-bottom:6px;line-height:1.3;";
  title.textContent = lib.name || "Library";
  top.appendChild(title);

  if (lib.address) {
    const addr = document.createElement("p");
    addr.style.cssText = "font-size:.88rem;color:#444;line-height:1.4;margin-bottom:10px;";
    addr.textContent = lib.address;
    top.appendChild(addr);
  }

  if (lib.phone) {
    const phone = document.createElement("p");
    phone.style.cssText = "font-size:.86rem;margin-bottom:8px;font-weight:500;color:var(--ink);";
    phone.innerHTML = `📞 Telephone: <a href="tel:${esc(lib.phone)}" style="font-weight:600">${esc(lib.phone)}</a>`;
    top.appendChild(phone);
  }

  card.appendChild(top);

  const footer = document.createElement("div");
  footer.style.cssText = "margin-top:14px;padding-top:12px;border-top:1px solid var(--ivory-400);display:flex;justify-content:space-between;align-items:center;font-size:.82rem;";

  const statusNote = document.createElement("span");
  statusNote.className = "muted";
  statusNote.textContent = lib.verification_status === "verified_location_and_contact"
    ? "✔ Location & Phone verified"
    : lib.location ? "✔ Location verified" : "Directory listing";
  footer.appendChild(statusNote);

  if (lib.directions_url) {
    const dirLink = document.createElement("a");
    dirLink.href = escUrl(lib.directions_url);
    dirLink.target = "_blank";
    dirLink.rel = "noopener noreferrer";
    dirLink.style.cssText = "font-weight:600;color:var(--green-700);text-decoration:underline;";
    dirLink.textContent = "Get Directions ↗";
    footer.appendChild(dirLink);
  }

  card.appendChild(footer);
  return card;
}

async function loadLibraries() {
  grid.innerHTML = `<p class="muted">Loading library records from uploaded dataset…</p>`;
  countEl.textContent = "";

  const hasFilter = state.q || (state.area && state.area !== "All") || state.category !== "all" || state.hasPhone || state.mode === "nearby";
  resetBtn.style.display = hasFilter ? "inline-block" : "none";

  try {
    let res;
    if (state.mode === "nearby" && state.userLocation) {
      res = await libraryService.nearby({
        lat: state.userLocation.lat,
        lon: state.userLocation.lon,
        radius_km: state.radiusKm,
        q: state.q,
        category: state.category !== "all" ? state.category : "",
        page: state.page,
        page_size: state.pageSize,
      });
    } else {
      res = await libraryService.search({
        q: state.q,
        area: state.area !== "All" ? state.area : "",
        category: state.category !== "all" ? state.category : "",
        has_phone: state.hasPhone ? true : null,
        page: state.page,
        page_size: state.pageSize,
      });
    }

    grid.innerHTML = "";
    const items = res.items || [];
    const total = res.total || 0;
    const pages = Math.max(1, Math.ceil(total / state.pageSize));

    if (state.mode === "nearby") {
      countEl.textContent = `${total} librar${total === 1 ? "y" : "ies"} within ${state.radiusKm} km of your location · Page ${state.page} of ${pages}`;
    } else {
      countEl.textContent = `${total} librar${total === 1 ? "y" : "ies"} found · Page ${state.page} of ${pages}`;
    }

    if (!items.length) {
      grid.innerHTML = `
        <div class="panel" style="grid-column: 1 / -1; text-align: center; padding: 40px 20px;">
          <b style="font-size: 1.1rem; color: var(--green-700)">No libraries found matching your criteria</b>
          <p class="muted" style="margin-top: .5rem">Try clearing the search query or selecting a different locality from the list above.</p>
        </div>
      `;
    } else {
      items.forEach(lib => grid.appendChild(renderLibraryCard(lib)));
    }

    prevBtn.disabled = state.page <= 1;
    nextBtn.disabled = state.page >= pages;
    pageInfo.textContent = `Page ${state.page} of ${pages}`;
  } catch (err) {
    grid.innerHTML = `
      <div class="panel" style="grid-column: 1 / -1; padding: 24px;">
        <b style="color: var(--amber)">Could not load libraries</b>
        <p class="muted" style="margin-top: .4rem">${esc(err.message || "Failed to reach library service")}</p>
      </div>
    `;
  }
}

// Event Listeners
main.querySelector("#lib-search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  state.q = main.querySelector("#lib-q").value.trim();
  state.page = 1;
  loadLibraries();
});

main.querySelectorAll("[data-area]").forEach(btn => {
  btn.addEventListener("click", () => {
    state.area = btn.dataset.area;
    state.page = 1;
    state.mode = "search";
    nearMeBox.style.display = "none";
    main.querySelectorAll("[data-area]").forEach(b => b.setAttribute("aria-pressed", b.dataset.area === state.area));
    loadLibraries();
  });
});

main.querySelector("#chk-phone").addEventListener("change", (e) => {
  state.hasPhone = e.target.checked;
  state.page = 1;
  loadLibraries();
});

main.querySelector("#sel-category").addEventListener("change", (e) => {
  state.category = e.target.value;
  state.page = 1;
  loadLibraries();
});

main.querySelector("#sel-radius").addEventListener("change", (e) => {
  state.radiusKm = parseFloat(e.target.value) || 5;
  state.page = 1;
  loadLibraries();
});

main.querySelector("#btn-near-me").addEventListener("click", () => {
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser. Please search by locality instead.");
    return;
  }
  nearMeStatus.textContent = "Requesting location permission…";
  nearMeBox.style.display = "flex";

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      state.userLocation = {
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
      };
      state.mode = "nearby";
      state.page = 1;
      nearMeStatus.textContent = `Coordinates detected (${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)})`;
      loadLibraries();
    },
    (err) => {
      nearMeStatus.textContent = "Location permission denied or unavailable. Please search by area.";
      state.mode = "search";
    },
    { timeout: 10000 }
  );
});

resetBtn.addEventListener("click", () => {
  state.q = "";
  state.area = "All";
  state.category = "all";
  state.hasPhone = false;
  state.mode = "search";
  state.userLocation = null;
  state.page = 1;
  main.querySelector("#lib-q").value = "";
  main.querySelector("#chk-phone").checked = false;
  main.querySelector("#sel-category").value = "all";
  nearMeBox.style.display = "none";
  main.querySelectorAll("[data-area]").forEach(b => b.setAttribute("aria-pressed", b.dataset.area === "All"));
  loadLibraries();
});

prevBtn.addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    loadLibraries();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});

nextBtn.addEventListener("click", () => {
  state.page += 1;
  loadLibraries();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

mountChrome("");
loadLibraries();
