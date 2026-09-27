/* Landing page view */
async function renderHome(){
  const v = document.getElementById("view");
  let cat;
  try { cat = await API.get("/api/catalog"); }
  catch(e){ v.innerHTML = `<div class="wrap"><p>Server se connect nahi ho paaya. Refresh karein.</p></div>`; return; }
  const tradeIcons = {electrician:"bulb", plumber:"droplet", carpenter:"tool", painter:"brush", cleaning:"wind",
    appliance:"snow", driver:"car", gardener:"leaf", cook:"pot", caregiver:"heart", pest:"bug"};
  const counts = {};
  for (const tr of cat.trades) counts[tr.key] = (cat.services_by_trade[tr.key]||[]).length;
  v.innerHTML = `
  <section class="hero wrap">
    <div>
      <h1>${t("heroTitle")}</h1>
      <p class="lead">${t("heroLead")}</p>
      <div class="hero-ctas">
        <button class="btn big" onclick="go('browse')">${t("ctaBook")} →</button>
        <button class="btn ghost big" onclick="openWorkerApply()">${t("ctaJoin")}</button>
      </div>
    </div>
    <div class="hero-side">
      <div class="hero-collage" aria-hidden="true">
        <img src="/static/img/m02.jpg" alt="">
        <img src="/static/img/f12.jpg" alt="">
        <img src="/static/img/m28.jpg" alt="">
        <img src="/static/img/f20.jpg" alt="">
      </div>
      <div class="hero-float">
        <span class="big">90%</span><br><span class="muted small">${t("statShare")}</span>
      </div>
  </div>
  </section>

  <div class="wrap stats-band">
    ${statCard(cat.stats.workers + "+", t("statWorkers"))}
    ${statCard(cat.stats.jobs.toLocaleString("en-IN"), t("statJobs"))}
    ${statCard(cat.stats.coops, t("statCoops"))}
    ${statCard(cat.stats.share + "%", t("statShare"))}
  </div>

  <section class="section wrap">
    <div class="section-head"><h2>${t("browseTitle")}</h2></div>
    <div class="trade-grid">
      ${cat.trades.map(tr => `
        <div class="trade-card" onclick="go('browse','${tr.key}')">
          <div class="trade-icon">${ic(tradeIcons[tr.key]||"tool", 22)}</div>
          <h3>${esc(LANG==="hi"?tr.hi:tr.en)}</h3>
          <span class="n">${counts[tr.key]||0} ${LANG==="hi"?"सर्विसेज़":"services"}</span>
        </div>`).join("")}
    </div>
  </section>

  <section class="section wrap">
    <div class="section-head"><h2>${LANG==="hi"?"कैसे चलता है":"How it works"}</h2></div>
    <div class="how-grid">
      <div class="how-step"><div class="step-num">1</div><h3>${t("how1t")}</h3><p>${t("how1d")}</p></div>
      <div class="how-step"><div class="step-num">2</div><h3>${t("how2t")}</h3><p>${t("how2d")}</p></div>
      <div class="how-step"><div class="step-num">3</div><h3>${t("how3t")}</h3><p>${t("how3d")}</p></div>
    </div>
  </section>

  <section class="section wrap">
    <div class="split-band">
      <div>
        <h2>${t("splitTitle")}</h2>
        <p>${t("splitBody")}</p>
      </div>
      <div class="vs">
        <div class="row ours"><b>90%</b> <span>${t("vsUs")}</span></div>
        <div class="row"><b style="color:#f0c9a8">75–80%</b> <span>${t("vsThem")}</span></div>
      </div>
    </div>
  </section>`;
}
function statCard(num, lbl){
  return `<div class="stat-card"><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`;
}

/* ---- worker apply modal (public) ---- */
let CATALOG = null;
async function getCatalog(){
  if(!CATALOG) CATALOG = await API.get("/api/catalog");
  return CATALOG;
}
async function openWorkerApply(){
  const cat = await getCatalog();
  modal(`
  <h2 style="margin-bottom:4px">${LANG==="hi"?"कामगार के रूप में जुड़ें":"Join as a Worker"}</h2>
  <p class="muted small" style="margin-bottom:18px">${LANG==="hi"
    ? "Apni labour cooperative ke through register karein. Verification ke baad verified badge milega."
    : "Register through your labour cooperative. Verified badge after the cooperative approves you."}</p>
  <div id="wa-err"></div>
  <div class="field"><label>${LANG==="hi"?"पूरा नाम":"Full name"}</label><input id="wa-name"></div>
  <div class="field"><label>${LANG==="hi"?"मोबाइल नंबर":"Mobile number"}</label><input id="wa-phone" placeholder="98XXXXXXXX"></div>
  <div class="field"><label>Password</label><input id="wa-pass" type="password"></div>
  <div class="card-grid two">
    <div class="field"><label>${LANG==="hi"?"काम (trade)":"Trade"}</label>
      <select id="wa-trade">${cat.trades.map(x=>`<option value="${x.key}">${esc(LANG==="hi"?x.hi:x.en)}</option>`).join("")}</select></div>
    <div class="field"><label>${LANG==="hi"?"सहकारी समिति":"Cooperative"}</label>
      <select id="wa-coop">${cat.cooperatives.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select></div>
  </div>
  <div class="card-grid two">
    <div class="field"><label>${LANG==="hi"?"अनुभव (साल)":"Experience (years)"}</label><input id="wa-exp" type="number" value="5" min="0" max="50"></div>
    <div class="field"><label>${LANG==="hi"?"प्रमाणपत्र (वैकल्पिक)":"Certificate (optional)"}</label><input id="wa-cert" placeholder="ITI / NSDC / Skill India..."></div>
  </div>
  <button class="btn big" style="width:100%" onclick="submitWorkerApply()">${LANG==="hi"?"आवेदन भेजें":"Submit Application"}</button>`);
}
async function submitWorkerApply(){
  try {
    const r = await API.post("/api/apply-worker", {
      name: val("wa-name"), phone: val("wa-phone"), password: val("wa-pass"),
      trade: val("wa-trade"), coop_id: +val("wa-coop"),
      exp_years: +val("wa-exp") || 3, cert_title: val("wa-cert")
    });
    saveSession(r.token, r.user);
    closeModal();
    toast(r.message);
    go("worker");
  } catch(e){
    document.getElementById("wa-err").innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
  }
}
function val(id){ return document.getElementById(id).value.trim(); }
