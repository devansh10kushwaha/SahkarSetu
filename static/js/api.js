/* API helper + session + shared UI utils */
const API = {
  token: localStorage.getItem("ss_token"),
  user: null,
  async req(path, opts = {}) {
    const headers = {"Content-Type": "application/json"};
    if (API.token) headers["Authorization"] = "Bearer " + API.token;
    const res = await fetch(path, {...opts, headers});
    if (res.status === 401 && path !== "/api/login") {
      logout(true); throw new Error("session-expired");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      // a refusal may carry structure (e.g. "worker busy" + a nearest-free alternative)
      const d = data.detail;
      if (d && typeof d === "object") {
        const err = new Error(d.message || res.statusText);
        err.detail = d; err.status = res.status;
        throw err;
      }
      throw new Error(d || res.statusText);
    }
    return data;
  },
  get(p){ return API.req(p); },
  post(p, b){ return API.req(p, {method:"POST", body: JSON.stringify(b||{})}); }
};
function saveSession(token, user){
  API.token = token; localStorage.setItem("ss_token", token);
  API.user = user; renderUserChip();
}
async function restoreSession(){
  if (!API.token) return false;
  try { API.user = await API.get("/api/me"); renderUserChip(); return true; }
  catch(e){ return false; }
}
function logout(silent){
  API.token = null; API.user = null; localStorage.removeItem("ss_token");
  renderUserChip(); go("home");
}
function renderUserChip(){
  const chip = document.getElementById("user-chip");
  const show = (id, on) => document.getElementById(id).classList.toggle("hidden", !on);
  const logged = !!API.user;
  show("btn-login", !logged); show("btn-logout", logged);
  show("nav-mybookings", logged && API.user.role==="customer");
  show("nav-worker", logged && API.user.role==="worker");
  show("nav-admin", logged && ["federation_admin","super_admin"].includes(API.user.role));
  show("nav-society", logged && API.user.role==="coop_admin");
  chip.innerHTML = logged
    ? `<span class="badge green" style="cursor:default">${esc(API.user.name.split(" ")[0])}</span>`
    : "";
}
function esc(s){ return String(s??"").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function toast(msg, ms=2600){
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(()=>el.remove(), ms);
}
function modal(html){
  document.getElementById("modal-root").innerHTML =
    `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal">${html}</div></div>`;
}
function closeModal(){ document.getElementById("modal-root").innerHTML = ""; }
function stars(r){ 
  const full = Math.round(r||0);
  return "★".repeat(full) + "☆".repeat(5-full);
}
function rupees(n){ return "₹" + Number(n||0).toLocaleString("en-IN"); }
function fmtDT(iso){
  if(!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {day:"numeric", month:"short", hour:"numeric", minute:"2-digit"});
}
const STATUS_HI = {requested:"नई request", accepted:"मंज़ूर", enroute:"रास्ते में", in_progress:"काम चालू", completed:"पूरा", cancelled:"रद्द"};
const STATUS_EN = {requested:"Requested", accepted:"Accepted", enroute:"On the way", in_progress:"Working", completed:"Completed", cancelled:"Cancelled"};
function stLabel(s){ return (LANG==="hi"?STATUS_HI:STATUS_EN)[s] || s; }
