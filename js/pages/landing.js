// Landing page — brand, hero with curiosity copy, two CTAs, genre chips,
// how-it-works. Still a pure landing page: no book cards, no catalogue.
import { bookService } from "../services/api.js";
import { authApi } from "../services/auth.js";
import { mountChrome } from "../ui.js";

const main = document.getElementById("main");

main.innerHTML = `
<section class="section hero" style="text-align:center">
  <p class="tag gold hero-eyebrow">ನಿಮ್ಮ ಆಸಕ್ತಿ · ನಿಮ್ಮ ಮುಂದಿನ ಪುಸ್ತಕ</p>
  <h1 class="hero-title">Every great story<br>begins with a little curiosity.</h1>
  <p class="muted" style="max-width:600px;margin:1.2rem auto 2rem">
    Some days call for a mystery. Some call for wisdom, wonder, or a story that
    feels like home. Tell us what sparks your curiosity, and PustakaMitra helps
    you discover your next favourite read — in Kannada or English.
  </p>
  <div class="hero-ctas" style="display:flex;gap:.8rem;justify-content:center;flex-wrap:wrap">
    <a class="btn" id="cta-primary" href="/pages/signup.html">Find your next book</a>
    <a class="btn secondary" href="#how">How it works</a>
  </div>
  <p class="muted" style="margin-top:2.4rem;font-size:1rem">
    ಕನ್ನಡವಾಗಲಿ, ಇಂಗ್ಲಿಷ್ ಆಗಲಿ — ನಿಮ್ಮ ಆಸಕ್ತಿಗೆ ಹೊಂದುವ ಮುಂದಿನ ಪುಸ್ತಕವನ್ನು ಒಟ್ಟಿಗೆ ಹುಡುಕೋಣ.<br>
    Kannada or English — let's find the next book that fits your curiosity.
  </p>
</section>

<section class="section" id="how">
  <h2 style="text-align:center">How PustakaMitra works</h2>
  <div class="how-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem;margin-top:2rem">
    <div class="panel how-step">
      <p class="how-num serif" style="color:var(--gold)">1</p>
      <h3>Tell us what you love reading</h3>
      <p class="muted">Pick the genres, languages, and reading pace that feel like you — a short, four-step onboarding.</p>
    </div>
    <div class="panel how-step">
      <p class="how-num serif" style="color:var(--gold)">2</p>
      <h3>Get suggestions that fit</h3>
      <p class="muted">We match real catalogue records to your interests and language preferences — and tell you why each pick was made.</p>
    </div>
    <div class="panel how-step">
      <p class="how-num serif" style="color:var(--gold)">3</p>
      <h3>Explore books</h3>
      <p class="muted">Open a book to see its details and, where verified catalogue information exists, library availability.</p>
    </div>
  </div>
</section>

<section class="section">
  <h2 style="text-align:center">Browse by genre</h2>
  <div class="chipbar" style="margin-top:1rem" id="genrechips"></div>
</section>`;

document.getElementById("genrechips").innerHTML = bookService.genres
  .map((g) => `<a class="chip" href="/pages/discover.html?genre=${g.id}" style="text-decoration:none">${g.en}<span class="kn">${g.kn}</span></a>`)
  .join("");

// subtle step reveal; skipped entirely when the user prefers reduced motion
const noMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const steps = document.querySelectorAll(".how-step");
if (noMotion) steps.forEach((el) => el.classList.add("in-view"));
else {
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in-view"); io.unobserve(e.target); } });
  }, { threshold: .2 });
  steps.forEach((el) => io.observe(el));
}

// Primary CTA follows the REAL session from the server (never localStorage):
// signed-in + interests → Discover · signed-in without → onboarding · else signup
(async () => {
  const a = document.getElementById("cta-primary");
  if (!a) return;
  let user = null;
  try { user = await authApi.me(); } catch { /* logged out / expired */ }
  if (user) {
    a.href = (user.interests || []).length ? "/pages/discover.html" : "/pages/onboarding.html";
  }
})();

mountChrome("Home");
