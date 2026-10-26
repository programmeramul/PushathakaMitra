// Sign-up / login — mirrored from Stitch auth screen (split editorial layout).
// Mock auth only: no credentials are stored or sent anywhere.
import { save } from "../services/api.js";
import { navbar } from "../ui.js";

const main = document.getElementById("main");
const current = window.location.hash === "#login" ? "login" : "signup";

main.innerHTML = `
<div class="split" style="margin-top:0">
  <aside class="left panel green" style="border-radius:0">
    <blockquote>“ಪುಸ್ತಕವು ಒಳ್ಳೆಯ ಗೆಳೆಯ; ಓದು ಮತ್ತಷ್ಟು ದಾರಿ ತೋರುವ ಬೆಳಕು.”</blockquote>
    <div class="by">A good book is a friend that lights the next path — in Kannada or English.</div>
    <div style="margin-top:auto" class="by">PustakaMitra AI · Bengaluru libraries edition</div>
  </aside>
  <section class="right"><div class="authcard">
    <h1 id="head">Create your reading profile</h1>
    <p class="muted" style="margin-bottom:1.5rem">Takes 2 minutes, then the recommendations roll in.</p>
    <form id="form">
      <div class="field" id="nameField"><label for="name">Full name</label><input id="name" required></div>
      <div class="field"><label for="email">Email</label><input id="email" type="email" required></div>
      <div class="field"><label for="pass">Password</label><input id="pass" type="password" minlength="6" required></div>
      <button class="btn" style="width:100%;margin-top:.5rem" type="submit">Create account</button>
    </form>
    <p style="margin-top:1rem">Already have an account? <a href="#login" id="toggle">Log in instead</a></p>
  </div></section>
</div>`;

let mode = current;
function paint() {
  main.querySelector("#head").textContent = mode === "login" ? "Welcome back" : "Create your reading profile";
  main.querySelector("#nameField").style.display = mode === "login" ? "none" : "";
  main.querySelector("button[type=submit]").textContent = mode === "login" ? "Log in" : "Create account";
  main.querySelector("#toggle").textContent = mode === "login" ? "Sign up instead" : "Log in instead";
  main.querySelector("#toggle").href = mode === "login" ? "#signup" : "#login";
}
paint();

main.querySelector("#toggle").addEventListener("click", (e) => { mode = mode === "login" ? "signup" : "login"; paint(); });

// Mock auth: accept anything, store the display name locally, jump to onboarding.
main.querySelector("#form").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = main.querySelector("#name").value.trim() || "Reader";
  save({ name, email: main.querySelector("#email").value.trim(), onboarded: false });
  window.location.href = "/pages/onboarding.html";
});

document.getElementById("nav").innerHTML = `<div class="inner"><a class="logo" href="/index.html"><span class="mark">ಪ</span>PustakaMitra AI</a><div class="links"><a href="/index.html" class="btn secondary small">← Back to home</a></div></div>`;
footer();

function footer() { document.getElementById("footer").outerHTML = ""; }
