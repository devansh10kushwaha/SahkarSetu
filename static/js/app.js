/* Router + auth view + boot */
const VIEWS = {
  home: renderHome,
  browse: renderBrowse,
  mybookings: renderMyBookings,
  worker: renderWorker,
  admin: renderAdmin,
  society: renderSociety
};
let CURRENT = "home";
function go(view, arg){
  if(view==="auth"){ renderAuth(); return; }
  CURRENT = view;
  const fn = VIEWS[view] || renderHome;
  fn(arg);
}
function rerender(){ go(CURRENT); }

/* ---- auth (login / customer signup) ---- */
function renderAuth(){
  document.getElementById("view").innerHTML = `
  <div class="auth-wrap">
    <div class="auth-card">
      <h1>${LANG==="hi"?"स्वागत है":"Welcome"}</h1>
      <p class="muted small" style="margin-bottom:18px">${LANG==="hi"?"Login karein ya naya account banayein":"Log in or create an account"}</p>
      <div class="auth-tabs">
        <button class="chip on" id="tab-login" onclick="authTab('login')">${t("login")}</button>
        <button class="chip" id="tab-signup" onclick="authTab('signup')">${LANG==="hi"?"नया ग्राहक":"New customer"}</button>
      </div>
      <div id="auth-err"></div>
      <div class="field"><label data-i18n-x="phone">${LANG==="hi"?"मोबाइल नंबर":"Mobile number"}</label>
        <input id="au-phone" placeholder="9000000001"></div>
      <div class="field"><label>Password</label><input id="au-pass" type="password"></div>
      <button class="btn big" style="width:100%" onclick="authSubmit()">${LANG==="hi"?"आगे →":"Go →"}</button>
      <div class="demo-box">
        <b>Demo accounts</b><br>
        ${ic("user",13)} Customer: <b>9000000001</b> / demo123<br>
        ${ic("tool",13)} Worker: <b>8000000001</b> / demo123<br>
        ${ic("home",13)} Federation admin: <b>7000000001</b> / admin123
      </div>
    </div>
  </div>`;
  window.AUTH_MODE = "login";
}
function authTab(m){
  window.AUTH_MODE = m;
  document.getElementById("tab-login").classList.toggle("on", m==="login");
  document.getElementById("tab-signup").classList.toggle("on", m==="signup");
  const extra = document.getElementById("au-name");
  if(m==="signup" && !extra){
    document.querySelector(".field").insertAdjacentHTML("beforebegin",
      `<div class="field"><label>${LANG==="hi"?"नाम":"Name"}</label><input id="au-name"></div>`);
  }
  if(extra) extra.parentElement.classList.toggle("hidden", m!=="signup");
  document.querySelector(".demo-box").style.display = m==="login" ? "" : "none";
}
async function authSubmit(){
  const err = document.getElementById("auth-err");
  err.innerHTML = "";
  try{
    if(window.AUTH_MODE === "signup"){
      const r = await API.post("/api/register-customer", {
        name: val("au-name"), phone: val("au-phone"), password: val("au-pass"), language: LANG
      });
      saveSession(r.token, r.user); toast((LANG==="hi"?"स्वागत, ":"Welcome, ")+r.user.name); go("browse");
    } else {
      const r = await API.post("/api/login", {phone: val("au-phone"), password: val("au-pass")});
      saveSession(r.token, r.user);
      toast((LANG==="hi"?"स्वागत, ":"Welcome, ")+r.user.name.split(" ")[0]);
      go({customer:"browse", worker:"worker", federation_admin:"admin", super_admin:"admin",
          coop_admin:"society"}[r.user.role] || "home");
    }
  }catch(e){ err.innerHTML = `<div class="form-error">${esc(e.message)}</div>`; }
}

/* ---- boot ---- */
(async function boot(){
  applyI18n();
  await restoreSession();
  go("home");
})();
