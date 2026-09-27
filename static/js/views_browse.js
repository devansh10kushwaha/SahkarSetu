/* Browse (list + map) + worker profile + booking flow */
let browseState = {trade:null, zone:null, map:null, markers:[], workers:[]};

async function renderBrowse(trade){
  const cat = await getCatalog();
  browseState.trade = trade || null;
  document.getElementById("view").innerHTML = `
  <div class="wrap" style="padding-top:28px">
    <div class="page-title">
      <h1>${LANG==="hi"?"verified मिस्त्री खोजें":"Find a verified worker"}</h1>
      <button class="btn ghost sm" onclick="go('home')">${LANG==="hi"?"← होम":"← Home"}</button>
    </div>
    <div class="filters" id="trade-chips">
      <button class="chip ${!browseState.trade?"on":""}" onclick="go('browse')">${LANG==="hi"?"सभी काम":"All trades"}</button>
      ${cat.trades.map(x=>`<button class="chip ${browseState.trade===x.key?"on":""}"
        onclick="go('browse','${x.key}')">${esc(LANG==="hi"?x.hi:x.en)}</button>`).join("")}
    </div>
    <div class="filters"><span class="muted small">${LANG==="hi"?"इलाक़ा:":"Area:"}</span>
      <button class="chip ${!browseState.zone?"on":""}" onclick="setZone(null)">${LANG==="hi"?"पूरा दिल्ली":"All Delhi"}</button>
      ${cat.zones.map(z=>`<button class="chip ${browseState.zone===z.key?"on":""}" onclick="setZone('${z.key}')">${esc(z.en)}</button>`).join("")}
    </div>
    <div class="browse-cols">
      <div id="worker-list"></div>
      <div id="map"></div>
    </div>
  </div>`;
  await loadWorkers();
  initMap();
}

function setZone(z){ browseState.zone = z; renderBrowse(browseState.trade); }

async function loadWorkers(){
  const p = new URLSearchParams();
  if(browseState.trade) p.set("trade", browseState.trade);
  if(browseState.zone) p.set("zone", browseState.zone);
  const data = await API.get("/api/workers?"+p.toString());
  browseState.workers = data.workers;
  const list = document.getElementById("worker-list");
  if(!data.workers.length){
    list.innerHTML = `<div class="card muted">Is filter mein koi verified worker nahi mila.</div>`;
    return;
  }
  list.innerHTML = data.workers.map(w=>`
    <div class="wrow" onclick="openProfile(${w.id})">
      <img class="avatar" src="${w.photo||"/static/img/w2.jpg"}" onerror="this.src='/static/img/w2.jpg'">
      <div class="info">
        <div class="nm">${esc(w.name)}
          <span class="badge green"><span class="dot"></span>${LANG==="hi"?"सहकारी-प्रमाणित":"Coop-verified"}</span>
          ${w.busy?`<span class="badge amber">${LANG==="hi"?"अभी व्यस्त":"Busy now"}</span>`:""}
        </div>
        <div class="meta">${esc(w.coop_name)} · ${w.exp_years} ${LANG==="hi"?"साल अनुभव":"yrs exp"} · ${w.jobs_done} ${LANG==="hi"?"काम":"jobs"}</div>
        <div class="meta" style="color:var(--amber)">${stars(w.rating_avg)} <span class="muted">${w.rating_avg||"—"} (${w.rating_count})</span></div>
      </div>
      <div class="price-tag"><div class="p">${rupees(w.avg_price)}</div><div class="muted small">${LANG==="hi"?"औसत":"avg"}</div></div>
    </div>`).join("");
}

let MAP, markerLayer;
function initMap(){
  if(MAP){ MAP.remove(); MAP=null; }
  MAP = L.map("map", {scrollWheelZoom:false}).setView([28.6139, 77.2090], 11);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "© OpenStreetMap contributors"
  }).addTo(MAP);
  markerLayer = L.layerGroup().addTo(MAP);
  plotMarkers();
}
function plotMarkers(){
  if(!MAP) return;
  markerLayer.clearLayers();
  for(const w of browseState.workers){
    if(!w.lat || !w.lng) continue;
    L.circleMarker([w.lat, w.lng], {radius:8, color:"#14503a", fillColor:"#1f6b47", fillOpacity:.9})
      .bindPopup(`<b>${esc(w.name)}</b><br>${esc(w.coop_name)}<br><a href="#" onclick="openProfile(${w.id});return false">${LANG==="hi"?"प्रोफ़ाइल देखें":"View profile"}</a>`)
      .addTo(markerLayer);
  }
  if(browseState.workers.length) {
    const pts = browseState.workers.filter(w=>w.lat).map(w=>[w.lat,w.lng]);
    if(pts.length) MAP.fitBounds(pts, {padding:[30,30], maxZoom:14});
  }
}

/* ---- profile modal ---- */
async function openProfile(wid){
  const d = await API.get(`/api/workers/${wid}`);
  const w = d.worker;
  modal(`
    <div style="display:flex;gap:16px;align-items:center;margin-bottom:16px">
      <img class="avatar" style="width:74px;height:74px" src="${w.photo}">
      <div>
        <h2 style="font-size:21px">${esc(w.name)}</h2>
        <div class="muted small">${esc(w.coop_name)} · ${w.exp_years} ${LANG==="hi"?"साल":"yrs"} · ${w.jobs_done} ${LANG==="hi"?"काम":"jobs"}</div>
        <div style="color:var(--amber);margin-top:3px">${stars(w.rating_avg)} <span class="muted small">${w.rating_avg||"—"} (${w.rating_count})</span></div>
      </div>
    </div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px">
      <span class="badge green"><span class="dot"></span>${LANG==="hi"?"सहकारी-प्रमाणित":"Coop-verified"}</span>
      ${w.busy?`<span class="badge amber">${LANG==="hi"?"अभी एक काम पर":"On a job right now"}</span>`:`<span class="badge green">${LANG==="hi"?"अभी free":"Free now"}</span>`}
      <span class="badge ${w.skill_level==="expert"?"green":w.skill_level==="skilled"?"blue":"amber"}">${ic("award",12)} ${skillLabel(w.skill_level)}</span>
      <span class="badge blue">₹${w.hourly_min}–${w.hourly_max} ${LANG==="hi"?"रेंज":"range"}</span>
      ${w.insured?`<span class="badge green">${ic("shield",12)} ${LANG==="hi"?"बीमित":"insured"}</span>`:""}
      ${d.welfare.map(x=>`<span class="badge amber">${ic("shield",12)} ${x.scheme}</span>`).join("")}
    </div>
    <p class="small" style="margin-bottom:14px">${esc(w.bio||"")}</p>
    ${d.certifications.length?`<h3 style="font-size:15px;margin-bottom:6px">${LANG==="hi"?"प्रमाणपत्र":"Certificates"}</h3>
      <ul style="margin:0 0 12px 18px;font-size:14px">${d.certifications.filter(c=>c.status==="verified").map(c=>`<li>${esc(c.title)} — ${esc(c.issuer)} (${c.year}) ${ic("check",11)}</li>`).join("") || `<li class="muted">${LANG==="hi"?"जाँच बाकी":"awaiting verification"}</li>`}</ul>`:""}
    ${d.reviews.length?`<h3 style="font-size:15px;margin-bottom:6px">${LANG==="hi"?"ग्राहकों की राय":"Recent reviews"}</h3>
      ${d.reviews.slice(0,3).map(r=>`<div class="kv"><span><span class="muted small">${esc(r.cust)}</span> · "${esc(r.comment)}"</span><b style="color:var(--amber)">${r.rating} ${ic("star",12)}</b></div>`).join("")}`:""}
    <h3 style="font-size:15px;margin:12px 0 8px">${LANG==="hi"?"इनकी सर्विसेज़ बुक करें":"Book their services"}</h3>
    ${d.services.map(s=>`<div class="kv"><span>${esc(LANG==="hi"?s.name_hi:s.name_en)} <span class="muted small">(₹${s.pmin}–${s.pmax})</span></span>
      <button class="btn sm" onclick='openBooking(${JSON.stringify({service_id:s.id, worker_id:(w.user_id!=null?w.user_id:w.id)})})'>${LANG==="hi"?"बुक":"Book"}</button></div>`).join("")}
  `);
}

/* ---- booking wizard ---- */
let BK = {};
async function openBooking(preset){
  if(!API.user){ toast(LANG==="hi"?"Pehle login karein":"Login first"); go("auth"); return; }
  if(API.user.role !== "customer"){ toast("Customer account se booking hoti hai"); return; }
  closeModal();
  BK = {service_id:preset.service_id, worker_id:preset.worker_id||null};
  const cat = await getCatalog();
  modal(`
  <h2 style="margin-bottom:14px">${LANG==="hi"?"बुकिंग — 2 छोटे steps":"Booking — 2 quick steps"}</h2>
  <div id="bk-body"></div>`);
  bkStep1();
}
function bkStep1(){
  const el = document.getElementById("bk-body");
  getCatalog().then(cat=>{
    el.innerHTML = `
    <div class="field"><label>${LANG==="hi"?"कब?":"When?"}</label>
      <select id="bk-when" onchange="bkWhenChange()">
        <option value="asap">${LANG==="hi"?"जल्द से जल्द (आज)":"As soon as possible (today)"}</option>
        <option value="tom">${LANG==="hi"?"कल सुबह (10 AM)":"Tomorrow morning (10 AM)"}</option>
        <option value="pick">${LANG==="hi"?"तारीख़ और समय ख़ुद चुनें":"Pick a date & time"}</option>
      </select></div>
    <div id="bk-when-pick" class="hidden">
      <div class="field"><label>${LANG==="hi"?"तारीख़":"Date"}</label><input type="date" id="bk-date"></div>
      <div class="field"><label>${LANG==="hi"?"समय":"Time"}</label><input type="time" id="bk-time" value="10:00" min="06:00" max="21:00"></div>
    </div>
    <div class="field"><label>${LANG==="hi"?"इलाक़ा":"Area"}</label>
      <select id="bk-zone">${cat.zones.map(z=>`<option value="${z.key}">${esc(z.en)}</option>`).join("")}</select></div>
    <div class="field"><label>${LANG==="hi"?"पूरा पता":"Full address"}</label>
      <input id="bk-addr" placeholder="${LANG==="hi"?"मकान/फ्लैट, गली, लैंडमार्क...":"House/flat, street, landmark..."}"></div>
    <div class="field"><label>${LANG==="hi"?"काम की जानकारी (वैकल्पिक)":"Job note (optional)"}</label>
      <textarea id="bk-notes" rows="2"></textarea></div>
    <label style="display:flex;gap:9px;align-items:center;font-size:14px;margin-bottom:16px">
      <input type="checkbox" id="bk-emg" style="width:auto">
      <span>${ic("bolt",14)} ${LANG==="hi"?"Emergency — अभी सबसे नज़दीकी free मिस्त्री चाहिए":"Emergency — need the nearest free worker NOW"}</span>
    </label>
    <button class="btn big" style="width:100%" onclick="bkNext()">${LANG==="hi"?"आगे →":"Next →"}</button>`;
  });
}
function bkWhenChange(){
  const v = val("bk-when");
  const box = document.getElementById("bk-when-pick");
  if(!box) return;
  box.classList.toggle("hidden", v!=="pick");
  if(v==="pick"){
    const di = document.getElementById("bk-date");
    const p = n => String(n).padStart(2,"0");
    const iso = dt => `${dt.getFullYear()}-${p(dt.getMonth()+1)}-${p(dt.getDate())}`;
    const now = new Date();
    di.min = iso(now);                                   // server rejects the past too
    di.max = iso(new Date(now.getTime() + 90*864e5));    // and anything beyond 90 days
    if(!di.value) di.value = iso(now);
  }
}
function bkNext(){
  BK.zone = val("bk-zone");
  BK.address = val("bk-addr");
  if(!BK.address){ alert("Address likhna zaroori hai"); return; }
  const whenSel = val("bk-when");
  let d = new Date();
  if(whenSel==="pick"){
    const dv = val("bk-date"), tv = val("bk-time") || "10:00";
    if(!dv){ alert(LANG==="hi"?"तारीख़ चुनें":"Pick a date"); return; }
    d = new Date(`${dv}T${tv}:00`);
    if(isNaN(d.getTime())){ alert(LANG==="hi"?"तारीख़/समय ठीक नहीं":"Bad date or time"); return; }
    const now = new Date();
    if(d < new Date(now.getTime() - 30*60000)){ alert(LANG==="hi"?"पुराना समय — आगे का चुनें":"That time has passed — pick a future slot"); return; }
    if(d > new Date(now.getTime() + 90*864e5)){ alert(LANG==="hi"?"90 दिन तक ही बुकिंग होती है":"Bookings go up to 90 days ahead"); return; }
  }
  else if(whenSel==="tom") d.setDate(d.getDate()+1), d.setHours(10,0,0,0);
  else d.setHours(Math.min(d.getHours()+2,19),0,0,0);
  BK.scheduled_for = localISO(d);   // local wall-clock, not UTC (toISOString shifted it)
  BK.notes = val("bk-notes");
  BK.is_emergency = document.getElementById("bk-emg").checked;
  bkStep2();
}
function localISO(d){
  const p = n => String(n).padStart(2,"0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
async function bkStep2(){
  const svc = await API.get("/api/catalog");
  let svcName = "", price = "";
  outer:
  for(const [tr, list] of Object.entries(svc.services_by_trade))
    for(const s of list)
      if(s.id===BK.service_id){
        svcName = LANG==="hi"?s.name_hi:s.name_en;
        price = "₹" + Math.round((s.pmin+s.pmax)/2);
        break outer;
      }
  document.getElementById("bk-body").innerHTML = `
    <div class="kv"><span>${LANG==="hi"?"Service":"Service"}</span><b>${svcName}</b></div>
    <div class="kv"><span>${LANG==="hi"?"अनुमानित रेट":"Estimated rate"}</span><b>${price} ${LANG==="hi"?"(काम के बाद confirm)":"(confirmed after job)"}</b></div>
    <div class="kv"><span>${LANG==="hi"?"कब":"When"}</span><b>${fmtDT(BK.scheduled_for)}</b></div>
    <div class="kv"><span>${LANG==="hi"?"पता":"Address"}</span><b style="max-width:220px">${esc(BK.address)}</b></div>
    <div class="kv"><span>${BK.is_emergency?ic("bolt",13)+" "+(LANG==="hi"?"Emergency match":"Emergency match"):LANG==="hi"?"मिलान":"Matching"}</span>
      <b>${BK.alt_of
            ? (LANG==="hi"?"नज़दीकी free: ":"Nearest free: ")+esc(BK.alt_of)
            : (LANG==="hi"? (BK.worker_id?"चुना हुआ मिस्त्री":"नज़दीकी free verified मिस्त्री") : (BK.worker_id?"Your chosen worker":"Nearest free verified worker"))}</b></div>
    <div id="bk-msg" style="margin:14px 0"></div>
    <button class="btn big" style="width:100%" onclick="bkConfirm()">${LANG==="hi"?"बुकिंग पक्की करें":"Confirm booking"} ${ic("check",15)}</button>`;
}
async function bkConfirm(){
  try{
    const r = await API.post("/api/bookings", BK);
    closeModal();
    toast((LANG==="hi"?"बुकिंग हो गई: ":"Booked: ")+r.code+" · "+r.worker.name+
          (r.worker.distance_km!=null ? " ("+r.worker.distance_km+" km)" : ""));
    go("mybookings");
  }catch(e){
    // Chosen worker is mid-job: never silently reroute, but give a one-tap way forward.
    const d = e.detail;
    if(d && d.busy){
      const alt = d.alternative;
      document.getElementById("bk-msg").innerHTML =
        `<div class="form-error">${esc(d.message||e.message)}</div>` +
        (alt?`<button class="btn sm" style="margin-top:10px" onclick="bkUseAlt(${alt.id},${JSON.stringify(alt.name)},${alt.distance_km??"null"})">
              ${LANG==="hi"?"इन्हें भेजें: ":"Book instead: "}${esc(alt.name)}${alt.distance_km!=null?" ("+alt.distance_km+" km)":""}</button>`:"");
      return;
    }
    document.getElementById("bk-msg").innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
  }
}

function bkUseAlt(id, name, km){
  BK.worker_id = id;
  BK.alt_of = name;                 // shown on step 2 so nobody is surprised
  bkStep2();
  document.getElementById("bk-msg").innerHTML =
    `<div class="muted small">${LANG==="hi"?"अब ":"Now sending to "}${esc(name)}${km!=null?" ("+km+" km)":""}</div>`;
}
