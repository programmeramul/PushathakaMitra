// Dashboard — real AI/keyword recommendations over the Mongo catalogue.
import { recommendationService } from "../services/api.js";
import { mountChrome, renderShelf } from "../ui.js";
import { requireAuth } from "../services/auth.js";

const main = document.getElementById("main");
const user = await requireAuth();
if (user) {
  let rec = null;
  try { rec = await recommendationService.forReader(); }
  catch (e) { rec = { engine: "error", message: e.message, items: [] }; }

  const label = rec.engine === "groq" ? "✦ Recommended for your interests — AI, from real catalogue records"
    : rec.engine === "keyword" ? "Picked by genre matching from the catalogue (AI suggestions unavailable right now)"
    : rec.engine === "no_interests" ? "No reading interests saved yet — <a href='/pages/onboarding.html'>complete onboarding</a> to get tailored picks"
    : rec.engine === "empty" ? "The catalogue is empty — nothing to recommend yet"
    : "Could not load recommendations right now";

  main.innerHTML = `
  <section class="section">
    <h1>Namaskara${user.name ? ", " + user.name : ""} 🙏</h1>
    <p class="muted">${(user.interests || []).length
      ? "Followed interests: " + user.interests.map((g) => g.replace(/-/g, " ")).join(", ")
      : "No interests selected yet — <a href='/pages/onboarding.html'>complete onboarding</a> to get tailored picks"}</p>
  </section>

  <section class="section">
    <h2>${rec.engine === "groq" ? "Recommended for your interests" : "Discover books"}</h2>
    <p class="muted" style="font-size:.9rem">${label}</p>
    <div class="shelf" style="margin-top:1rem" id="recs"></div>
  </section>`;

  renderShelf(main.querySelector("#recs"), rec.items || [], { reason: rec.engine === "groq" || rec.engine === "keyword", engine: rec.engine });
  mountChrome("Discover");
}
