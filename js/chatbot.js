// PustakaMitra AI — personal reading companion (floating chat widget).
// Server-side auth decides availability (mountChrome → initChatbot); this
// module never decides "you are logged in" from localStorage.
// Conversation lives in browser memory only (sessionStorage), never Git/Mongo.
import { authApi } from "./services/auth.js";

const PANEL_ID = "pmchat";
const STORE_KEY = "pustakamitra.chat.v1";   // sessionStorage, cleared on logout

const CHIPS = [
  "Find my next book",
  "Recommend Kannada books",
  "Explore my interests",
  "Find libraries in Bengaluru",
  "Find books about business",
  "Recommend a book for a beginner",
];

// model/user text is ALWAYS rendered via textContent — model output never
// becomes HTML (XSS-safe by construction).
function bubble(role, text) {
  const b = document.createElement("div");
  b.className = "chatmsg " + role;
  const p = document.createElement("p");
  p.textContent = text;
  b.appendChild(p);
  return b;
}

function bookCard(b) {
  const a = document.createElement("a");
  a.className = "chatbook";
  a.href = `/pages/book.html?id=${encodeURIComponent(b.id)}`;
  const img = document.createElement("img");
  img.alt = "";
  img.src = b.cover_url || "";
  if (!b.cover_url) img.hidden = true;
  const meta = document.createElement("span");
  const title = document.createElement("b");
  title.textContent = b.title;
  const sub = document.createElement("small");
  sub.textContent = `${(b.authors || []).join(", ") || "Author not recorded"}` +
    (b.year ? ` · ${b.year}` : "") + (b.language ? ` · ${b.language}` : "");
  meta.append(title, sub);
  if (b.reason) {
    const r = document.createElement("small");
    r.className = "chatreason";
    r.textContent = b.reason;
    meta.append(r);
  }
  a.append(img, meta);
  return a;
}

function escUrl(u) { return String(u || "").replace(/"/g, "%22"); }

function linksBox(lib) {
  const w = document.createElement("div");
  w.className = "chatlib";
  const note = document.createElement("p");
  note.textContent = lib.note || "";
  w.appendChild(note);
  (lib.links || []).forEach((l) => {
    const a = document.createElement("a");
    a.href = escUrl(l.url); a.target = "_blank"; a.rel = "noopener noreferrer";
    a.textContent = l.label + " ↗";
    w.appendChild(a);
    w.appendChild(document.createElement("br"));
  });
  return w;
}

async function initChatbot(interests = []) {
  if (document.getElementById(PANEL_ID)) return;   // already mounted
  const root = document.createElement("div");
  root.id = PANEL_ID;
  document.body.appendChild(root);

  const saved = (() => { try { return JSON.parse(sessionStorage.getItem(STORE_KEY)) || []; } catch { return []; } })();
  const state = { open: false, busy: false, history: saved };

  root.innerHTML = `
  <button class="chat-fab" id="chatfab" aria-label="Open reading companion" title="Reading companion">
    <img src="/favicon.svg" alt="" width="26" height="26">
  </button>
  <section class="chat-panel" id="chatpanel" hidden aria-label="PustakaMitra AI chat" role="dialog">
    <header>
      <img src="/favicon.svg" alt="" width="24" height="24">
      <div><b>PustakaMitra AI</b><small>Your personal reading companion</small></div>
      <button id="chatclose" aria-label="Close chat">✕</button>
    </header>
    <div id="chatlog" class="chatlog" role="log" aria-live="polite"></div>
    <div class="chatchips" id="chatchips"></div>
    <form id="chatform" class="chatform">
      <input id="chatinput" type="text" maxlength="600" placeholder="Ask about books, genres, libraries…" aria-label="Message">
      <button class="btn small" type="submit" id="chatsend" aria-label="Send">Send</button>
    </form>
  </section>`;

  const panel = document.getElementById("chatpanel");
  const log = document.getElementById("chatlog");
  const input = document.getElementById("chatinput");

  const rerenderHistory = () => {
    log.innerHTML = "";
    if (!state.history.length) {
      log.appendChild(bubble("bot", "Namaskara! What would you love to read today?"));
      if (!interests.length)
        log.appendChild(bubble("system", "Complete onboarding so I can tailor picks to your interests."));
    }
    for (const h of state.history) log.appendChild(bubble(h.role, h.content || ""));
    log.appendChild(bubble("system", "Book picks below come from real Open Library records; Bengaluru library answers use official search links only (no verified holdings data yet)."));
    log.scrollTop = log.scrollHeight;
  };

  document.getElementById("chatfab").addEventListener("click", () => {
    const open = !state.open;
    panel.hidden = !open; state.open = open;
    if (state.open) { input.focus(); if (!state.rendered) { rerenderHistory(); state.rendered = true; } }
  });
  document.getElementById("chatclose").addEventListener("click", () => { panel.hidden = true; state.open = false; });

  const chips = document.getElementById("chatchips");
  CHIPS.forEach((q) => {
    const c = document.createElement("button");
    c.type = "button"; c.className = "chip chat-chip"; c.textContent = q;
    c.addEventListener("click", () => { input.value = q; send(); });
    chips.appendChild(c);
  });

  async function send() {
    const msg = input.value.trim();
    if (!msg || state.busy) return;
    input.value = "";
    log.appendChild(bubble("user", msg)); log.scrollTop = log.scrollHeight;
    state.history.push({ role: "user", content: msg });
    state.busy = true;
    document.getElementById("chatsend").disabled = true;
    grpLoading();

    try {
      const body = { message: msg, history: state.history.slice(-10).map(h => h) };
      const res = await fetch("http://127.0.0.1:8001/api/chat", {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await res.json();
      if (!res.ok) throw new Error((d.detail && d.detail.message) || "Chat service unavailable");
      const loading = document.getElementById("chatloading");
      if (loading) loading.remove();
      log.appendChild(bubble("bot", d.reply || ""));
      (d.books || []).slice(0, 5).forEach((b) => { const c = bookCard(b); c.className += " chatbookline"; log.appendChild(c); });
      if (d.library) log.appendChild(linksBox(d.library));
      state.history.push({ role: "bot", content: d.reply || "" });
      sessionStorage.setItem(STORE_KEY, JSON.stringify(state.history.slice(-20)));
      log.scrollTop = log.scrollHeight;
    } catch (e) {
      const loading = document.getElementById("chatloading");
      if (loading) loading.textContent = `Couldn't reach the chat service — no sample answer shown. (${e.message || "error"}) `;
      const r = document.createElement("button");
      r.className = "chip"; r.textContent = "Retry";
      r.addEventListener("click", () => {
        state.busy = false; document.getElementById("chatsend").disabled = false;
        input.value = msg; send();
      });
      loading && loading.appendChild(r);
    } finally {
      state.busy = false;
      document.getElementById("chatsend").disabled = false;
    }
  }

  function grpLoading() {
    const wrap = document.createElement("div");
    wrap.className = "chatmsg bot"; wrap.id = "chatloading";
    const p = document.createElement("p");
    p.textContent = "PustakaMitra is thinking…";
    wrap.appendChild(p); log.appendChild(wrap); log.scrollTop = log.scrollHeight;
  }

  document.getElementById("chatform").addEventListener("submit", (e) => { e.preventDefault(); send(); });

  rerenderHistory();
  state.rendered = true;
}

// logout cleanup: kill stored history + DOM everywhere
export function destroyChatbot() {
  const el = document.getElementById(PANEL_ID);
  if (el) el.remove();
  sessionStorage.removeItem(STORE_KEY);
}

export { initChatbot };
