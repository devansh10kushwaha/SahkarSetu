/* Federation Admin dashboard */
let ADM = {tab:"overview", forecast:null, map:null};

async function renderAdmin(){
  const v = document.getElementById("view");
  v.innerHTML = `
  <div class="app-layout">
    <aside class="app-side">
      <nav class="side-nav">
        ${[["overview","chart","Overview","ओवरव्यू"],
           ["verify","award","Verification","वेरिफिकेशन"],
           ["certs","award","Certificates","प्रमाणपत्र"],
           ["payouts","card","Payouts","पे-आउट"],
           ["welfare","shield","Welfare","कल्याण"],
           ["allocation","users","Allocation","आवंटन"],
           ["forecast","activity","Demand Forecast","डिमांड फ़ोरकास्ट"]].map(([k, icn, en, hi]) => [k, ic(icn,14)+" "+(LANG==="hi"?hi:en)])
          .map(([k,lbl])=>`<button class="${ADM.tab===k?"on":""}" onclick="admTab('${k}')">${lbl}</button>`).join("")}
      </nav>
    </aside>
    <div class="app-main" id="adm-main"><p class="muted">Loading…</p></div>
  </div>`;
  admTab(ADM.tab);
}

function admTab(tab){
  ADM.tab = tab;
  renderAdminTabs();
  ({overview:admOverview, verify:admVerify, certs:admCerts, payouts:admPayouts,
    welfare:admWelfare, allocation:admAllocation, forecast:admForecast})[tab]();
}

function renderAdminTabs(){
  const main = document.getElementById("view");
  if(!main.querySelector(".app-side")) return renderAdmin();
  document.querySelectorAll(".side-nav button").forEach((b,i)=>{
    b.classList.toggle("on", ["overview","verify","certs","payouts","welfare","allocation","forecast"][i]===ADM.tab);
  });
}

async function admOverview(){
  const el = document.getElementById("adm-main");
  const d = await API.get("/api/a/overview");
  const s = d.stats;
  el.innerHTML = `
    <h1 style="font-size:23px;margin-bottom:18px">${LANG==="hi"?"फ़ेडरेशन डैशबोर्ड":"Federation Dashboard"}</h1>
    <div class="stats-band" style="grid-template-columns:repeat(4,1fr);padding-top:0">
      ${statCard(s.workers_verified+"/"+s.workers_total, LANG==="hi"?"verified कामगार":"verified workers")}
      ${statCard(s.bookings_today, LANG==="hi"?"आज की बुकिंग":"bookings today")}
      ${statCard("₹"+Number(s.week_gmv).toLocaleString("en-IN"), LANG==="hi"?"हफ़्ते का GMV":"week GMV")}
      ${statCard(s.worker_share_pct+"%", LANG==="hi"?"कामगार का हिस्सा":"worker share")}
    </div>
    <div class="card-grid two" style="margin-top:6px">
      <div class="card"><h3>${LANG==="hi"?"अभी चालू काम":"Active jobs"} (${d.active_jobs.length})</h3>
        ${d.active_jobs.slice(0,8).map(j=>`
          <div class="kv"><span>${j.is_emergency?ic("bolt",12)+" ":""}${esc(j.service)} — ${esc(j.wname||"matching…")}</span>
          <b><span class="badge blue">${stLabel(j.status)}</span></b></div>`).join("") || '<p class="muted small">—</p>'}
      </div>
      <div class="card"><h3>${LANG==="hi"?"हफ़्ते भर के काम (trade-wise)":"This week by trade"}</h3>
        ${d.week_by_trade.map(r=>`
          <div class="kv"><span>${esc(r.trade)}</span><b>${r.n} ${LANG==="hi"?"काम":"jobs"}</b></div>`).join("") || '<p class="muted small">—</p>'}
      </div>
    </div>
    <div class="card"><h3>${LANG==="hi"?"हाल की बुकिंग":"Latest bookings"}</h3>
      <table class="tbl"><tr><th>Code</th><th>${LANG==="hi"?"सर्विस":"Service"}</th><th>${LANG==="hi"?"मिस्त्री":"Worker"}</th><th>Status</th><th>₹</th></tr>
      ${d.recent_bookings.map(b=>`<tr>
        <td class="muted small">${esc(b.code)}</td><td>${esc(b.service)}</td>
        <td>${esc(b.wname||"—")} ${b.is_emergency?ic("bolt",11):""}</td>
        <td><span class="badge blue">${stLabel(b.status)}</span></td>
        <td>${rupees(b.price||0)}</td></tr>`).join("")}
      </table>
    </div>`;
}

async function admVerify(){
  const el = document.getElementById("adm-main");
  const d = await API.get("/api/a/pending-workers");
  el.innerHTML = `
    <h1 style="font-size:23px;margin-bottom:6px">${LANG==="hi"?"वेरिफिकेशन क़तार":"Verification Queue"}</h1>
    <p class="muted" style="margin-bottom:18px">${LANG==="hi"?"Cooperative membership + प्रमाणपत्र check करके verified badge दें।":"Check cooperative membership and certificates, then grant the verified badge."}</p>
    ${d.pending.length ? d.pending.map(w=>`
      <div class="card">
        <div style="display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap">
          <div>
            <b>${esc(w.name)}</b> <span class="muted small">${esc(w.phone)}</span>
            <div class="muted small">${esc(w.trade)} · ${w.exp_years} ${LANG==="hi"?"साल":"yrs"} · ${esc(w.coop)}</div>
            <div class="muted small">e-Shram UAN: ${esc(w.e_shram_uan)}</div>
            ${w.certifications.map(c=>`<span class="badge amber">${ic("award",12)} ${esc(c.title)} (${c.year})</span>`).join("")}
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <button class="btn sm" onclick="doVerify(${w.id},true)">${ic("check",12)} ${LANG==="hi"?"मंज़ूर":"Approve"}</button>
            <button class="btn sm danger" onclick="doVerify(${w.id},false)">${LANG==="hi"?"नामंज़ूर":"Reject"}</button>
          </div>
        </div>
      </div>`).join("")
    : `<div class="card muted">${LANG==="hi"?"क़तार खाली है — सब verified हैं।":"Queue empty — everyone processed."}</div>`}`;
}
async function doVerify(wid, approve){
  try{
    await API.post(`/api/a/verify/${wid}`, {approve});
    toast(approve?(LANG==="hi"?"Verified":"Verified"):(LANG==="hi"?"Reject हुआ":"Rejected"));
    admVerify();
  }catch(e){ toast(e.message); }
}

async function admPayouts(){
  const el = document.getElementById("adm-main");
  const d = await API.get("/api/a/payouts");
  const today = new Date();
  const end = today.toISOString().slice(0,10);
  const start = new Date(today - 7*864e5).toISOString().slice(0,10);
  el.innerHTML = `
    <h1 style="font-size:23px;margin-bottom:18px">${LANG==="hi"?"पे-आउट रन":"Payout Runs"}</h1>
    <div class="card">
      <h3>${LANG==="hi"?"नया पे-आउट चलाएँ":"Run a new payout"}</h3>
      <div style="display:flex;gap:10px;align-items:end;flex-wrap:wrap">
        <div class="field" style="margin:0"><label>${LANG==="hi"?"से":"From"}</label><input type="date" id="po-start" value="${start}"></div>
        <div class="field" style="margin:0"><label>${LANG==="hi"?"तक":"To"}</label><input type="date" id="po-end" value="${end}"></div>
        <button class="btn" onclick="runPayout()">${LANG==="hi"?"▶ चलाएँ":"▶ Run"}</button>
      </div>
      <div id="po-result"></div>
    </div>
    <h3 style="margin:16px 0 10px">${LANG==="hi"?"पुराने रन":"Past runs"}</h3>
    <table class="tbl"><tr><th>#</th><th>${LANG==="hi"?"अवधि":"Period"}</th><th>${LANG==="hi"?"कामगार":"Workers"}</th><th>${LANG==="hi"?"काम":"Jobs"}</th><th>${LANG==="hi"?"मिस्त्रियों को":"To workers"}</th><th>10% fee</th></tr>
    ${d.runs.map(r=>`<tr><td>${r.id}</td><td class="muted small">${r.period_start} → ${r.period_end}</td>
      <td>${r.worker_count}</td><td>${r.job_count}</td>
      <td><b style="color:var(--green-dark)">${rupees(r.total_net)}</b></td><td class="muted">${rupees(r.total_commission)}</td></tr>`).join("")}
    </table>`;
}
async function runPayout(){
  const body = {period_start:val("po-start"), period_end:val("po-end")};
  try{
    let r;
    try{
      r = await API.post("/api/a/payouts/run", body);
    }catch(e){
      // duplicate period -> backend asks for explicit confirmation before re-running
      if(!/already ho chuka/.test(e.message)) throw e;
      if(!confirm(e.message)) return;
      r = await API.post("/api/a/payouts/run", {...body, confirm_duplicate:true});
    }
    document.getElementById("po-result").innerHTML = `
      <div class="card" style="margin-top:14px;background:var(--green-tint)">
        <b>${ic("check",13)} ${LANG==="hi"?`₹${r.total_net.toLocaleString("en-IN")} ${r.workers} कामगारों को`:`Rs ${r.total_net.toLocaleString("en-IN")} to ${r.workers} workers`}</b>
        <p class="muted small">${LANG==="hi"?"CSV तैयार है — federation bank transfer में use करें।":"CSV ready for the federation's bank transfer."}
        <a href="/api/a/payouts/csv/${r.run_id}?t=${API.token}" target="_blank">${LANG==="hi"?"CSV खोलें":"Open CSV"}</a></p>
      </div>`;
  }catch(e){ toast(e.message); }
}

async function admWelfare(){
  const el = document.getElementById("adm-main");
  const [d, rq] = await Promise.all([API.get("/api/a/welfare"), API.get("/api/a/welfare/requests")]);
  el.innerHTML = `
    <h1 style="font-size:23px;margin-bottom:6px">${LANG==="hi"?"कल्याण केंद्र":"Welfare Centre"}</h1>
    <p class="muted" style="margin-bottom:16px">${d.totals.pmsby_cost_note} · ${d.totals.pmjjby_cost_note}</p>
    ${(rq.enrolments.length || rq.claims.length) ? `
    <div class="card" style="border-left:3px solid var(--amber)">
      <h3>${ic("shield",14)} ${LANG==="hi"?"कामगारों के आवेदन (निर्णय बाकी)":"Worker applications awaiting a decision"}</h3>
      ${rq.enrolments.map(r=>`
        <div class="kv" style="align-items:center">
          <span>${ic("shield",12)} <b>${esc(r.name)}</b> — ${esc(r.scheme)}
            <span class="muted small">${esc(r.coop)}</span></span>
          <span style="white-space:nowrap">
            <button class="btn sm" onclick="admWelfareDecide(${r.worker_id},'${r.scheme}',true)">${LANG==="hi"?"मंज़ूर":"Approve"}</button>
            <button class="btn sm danger" onclick="admWelfareDecide(${r.worker_id},'${r.scheme}',false)">${LANG==="hi"?"नामंज़ूर":"Reject"}</button>
          </span></div>`).join("")}
      ${rq.claims.map(c=>`
        <div class="kv" style="align-items:center">
          <span>${ic("receipt",12)} <b>${esc(c.name)}</b> — ${esc(c.scheme)} ${LANG==="hi"?"क्लेम":"claim"}
            <span class="muted small">${esc(c.reason||"")} · ₹${c.amount||0} · ${esc(c.coop)}</span></span>
          <span style="white-space:nowrap">
            <button class="btn sm" onclick="admClaimDecide(${c.id},true)">${LANG==="hi"?"मंज़ूर":"Approve"}</button>
            <button class="btn sm danger" onclick="admClaimDecide(${c.id},false)">${LANG==="hi"?"नामंज़ूर":"Reject"}</button>
          </span></div>`).join("")}
    </div>` : ""}
    <div class="stats-band" style="grid-template-columns:repeat(3,1fr);padding-top:0;margin-bottom:16px">
      ${statCard(d.totals.pmsby, "PMSBY "+(LANG==="hi"?"जुड़े":"enrolled"))}
      ${statCard(d.totals.pmjjby, "PMJJBY "+(LANG==="hi"?"जुड़े":"enrolled"))}
      ${statCard(d.totals.verified, LANG==="hi"?"कुल verified":"total verified")}
    </div>
    <div class="card" style="padding:8px 18px;max-height:520px;overflow-y:auto">
      <table class="tbl"><tr><th>${LANG==="hi"?"कामगार":"Worker"}</th><th>${LANG==="hi"?"समिति":"Co-op"}</th><th>Kaam</th><th>${LANG==="hi"?"कवर":"Cover"}</th><th></th></tr>
      ${d.workers.map(w=>{
        const hasP = (w.schemes||"").includes("PMSBY");
        const hasJ = (w.schemes||"").includes("PMJJBY");
        return `<tr><td>${esc(w.name)}</td><td class="muted small">${esc(w.coop)}</td><td class="muted small">${esc(w.trade)}</td>
        <td>${hasP?'<span class="badge green">PMSBY</span> ':''}${hasJ?'<span class="badge green">PMJJBY</span>':''}${!hasP&&!hasJ?'<span class="badge red">'+(LANG==="hi"?"बिना कवर":"uncovered")+"</span>":""}</td>
        <td style="white-space:nowrap">
          ${!hasP?`<button class="btn sm ghost" onclick="enroll(${w.id},'PMSBY')">+ PMSBY</button>`:""}
          ${!hasJ?`<button class="btn sm ghost" onclick="enroll(${w.id},'PMJJBY')">+ PMJJBY</button>`:""}
        </td></tr>`;}).join("")}
      </table>
    </div>`;
}
async function enroll(wid, scheme){
  try{ await API.post("/api/a/welfare/enroll", {worker_id:wid, scheme}); toast(scheme); admWelfare(); }
  catch(e){ toast(e.message); }
}
async function admWelfareDecide(wid, scheme, approve){
  try{ await API.post("/api/a/welfare/decide", {worker_id:wid, scheme, approve});
       toast(scheme+" "+(approve?(LANG==="hi"?"मंज़ूर":"approved"):(LANG==="hi"?"नामंज़ूर":"rejected")));
       admWelfare(); }
  catch(e){ toast(e.message); }
}
async function admClaimDecide(cid, approve){
  try{ await API.post(`/api/a/welfare/claim/${cid}`, {approve});
       toast(LANG==="hi"?"क्लेम अपडेट हुआ":"Claim updated"); admWelfare(); }
  catch(e){ toast(e.message); }
}

/* ---- certificate verification queue (a cert only counts once a cooperative blesses it) ---- */
async function admCerts(){
  const el = document.getElementById("adm-main");
  const d = await API.get("/api/a/certs/pending");
  el.innerHTML = `
    <h1 style="font-size:23px;margin-bottom:6px">${LANG==="hi"?"प्रमाणपत्र जाँच":"Certificate Verification"}</h1>
    <p class="muted" style="margin-bottom:16px">${LANG==="hi"?"कामगार खुद जोड़े गए प्रमाणपत्र समिति की मंज़ूरी के बाद ही कौशल प्रोफ़ाइल में गिने जाते हैं।":"Self-declared certificates count toward the skill profile only after a cooperative verifies them."}</p>
    ${d.pending.length ? d.pending.map(c=>`
      <div class="card" style="padding:12px 18px">
        <div style="display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:center">
          <div>${ic("award",13)} <b>${esc(c.title)}</b>
            <div class="muted small">${esc(c.issuer||"Self-declared")} · ${c.year||"—"} · ${esc(c.name)} · ${esc(c.coop)}</div></div>
          <div style="white-space:nowrap">
            <button class="btn sm" onclick="admCertDecide(${c.id},true)">${ic("check",12)} ${LANG==="hi"?"मंज़ूर":"Verify"}</button>
            <button class="btn sm danger" onclick="admCertDecide(${c.id},false)">${LANG==="hi"?"नामंज़ूर":"Reject"}</button>
          </div></div>
      </div>`).join("")
    : `<div class="card muted">${LANG==="hi"?"क़तार खाली है — हर प्रमाणपत्र जाँचा जा चुका।":"Queue empty — every certificate reviewed."}</div>`}`;
}
async function admCertDecide(cid, approve){
  try{ await API.post(`/api/a/certs/${cid}`, {approve});
       toast(approve?(LANG==="hi"?"प्रमाणपत्र verified":"Certificate verified"):(LANG==="hi"?"नामंज़ूर":"Rejected"));
       admCerts(); }
  catch(e){ toast(e.message); }
}

/* ---- workforce allocation board: forecast demand vs verified supply ---- */
async function admAllocation(){
  const el = document.getElementById("adm-main");
  const d = await API.get("/api/a/allocation");
  const sevBadge = s => ({critical:"red", deficit:"amber", surplus:"blue", ok:"green"}[s]||"blue");
  el.innerHTML = `
    <h1 style="font-size:23px;margin-bottom:6px">${LANG==="hi"?"आवंटन बोर्ड":"Workforce Allocation"}</h1>
    <p class="muted" style="margin-bottom:16px">${esc(d.note)}</p>
    <table class="tbl"><tr><th>${LANG==="hi"?"इलाक़ा":"Zone"}</th><th>Trade</th>
      <th>${LANG==="hi"?"7 दिन की डिमांड":"Forecast 7d"}</th><th>${LANG==="hi"?"verified":"verified"}</th>
      <th>${LANG==="hi"?"अभी free":"free now"}</th><th>${LANG==="hi"?"सिफ़ारिश":"Action"}</th></tr>
    ${d.rows.slice(0,40).map(r=>`<tr>
      <td>${esc(r.zone)}</td><td class="muted small">${esc(r.trade)}</td>
      <td><b>${r.forecast_7d}</b></td><td>${r.verified}${r.pending?` <span class="muted small">(+${r.pending} q)</span>`:""}</td>
      <td>${r.free_now}</td>
      <td><span class="badge ${sevBadge(r.severity)}">${r.severity}</span> <span class="small">${esc(r.action)}</span></td>
    </tr>`).join("")}
    </table>`;
}

async function admForecast(){
  const el = document.getElementById("adm-main");
  if(!ADM.forecast) ADM.forecast = await API.get("/api/a/forecast");
  const fc = ADM.forecast;
  // build zone x dow matrix of total predicted demand
  const zones = [...new Set(fc.rows.map(r=>r.zone))].sort();
  const dows = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const grid = {};
  for(const r of fc.rows){
    const key = r.zone+"|"+r.dow;
    grid[key] = (grid[key]||0) + r.predicted;
  }
  const maxVal = Math.max(...Object.values(grid), 1);
  el.innerHTML = `
    <h1 style="font-size:23px;margin-bottom:6px">${LANG==="hi"?"डिमांड फ़ोरकास्ट — अगले 7 दिन":"Demand Forecast — next 7 days"}</h1>
    <p class="muted" style="margin-bottom:14px">${fc.model} · ${fc.window}. ${LANG==="hi"?"AI सिर्फ़ सुझाव देता है — फ़ैसला सहकारी समिति लेती है।":"The AI only advises — the cooperative decides."}</p>
    <button class="btn sm ghost" onclick="showSignals()" style="margin-bottom:14px">${ic("warn",14)} ${LANG==="hi"?"स्टाफ़िंग सुझाव देखें":"Show staffing suggestions"}</button>
    <div id="signals-box"></div>
    <div class="card heatmap"><h3>${LANG==="hi"?"इलाक़ा × दिन demand heatmap":"Zone × day heatmap"}</h3>
      <table class="hm-table">
        <tr><th></th>${dows.map(x=>`<th>${x}</th>`).join("")}</tr>
        ${zones.map(z=>`<tr><th style="text-align:left">${esc(z)}</th>
          ${dows.map(dw=>{
            const val = grid[z+"|"+dw]||0;
            const inten = val/maxVal;
            return `<td class="hm-cell" title="${z} ${dw}: ~${val.toFixed(1)} jobs/day"
              style="background:rgba(31,107,71,${(inten*0.85).toFixed(2)});color:${inten>0.5?"#fff":"inherit"}"
              onclick="zoneDetail('${z}')">${val.toFixed(1)}</td>`;}).join("")}
        </tr>`).join("")}
      </table>
    </div>
    <p class="muted small">${LANG==="hi"?"Cell par click karein — us zone ka trade-level breakdown dikhega.":"Click any cell for that zone's trade-level breakdown."}</p>`;
}
function showSignals(){
  API.get("/api/a/forecast/summary").then(d=>{
    document.getElementById("signals-box").innerHTML = d.top.length ? `
      <div class="card" style="background:var(--amber-tint)">
        <h3>${ic("warn",16)} ${LANG==="hi"?`${d.total_signals} jagah par staff kam pad sakta hai`:`${d.total_signals} staffing gaps found`}</h3>
        ${d.top.slice(0,6).map(r=>`<div class="suggest-row kv" style="border-radius:6px;padding:7px 9px">
          <span><b>${r.dow}</b> · ${esc(r.zone)} · ${esc(r.trade)} — ${LANG==="hi"?"demand":"demand"} ~${r.predicted}, ${LANG==="hi"?"उपलब्ध":"available"}: ${r.workers_available}</span>
          <b>${esc(r.suggest)}</b></div>`).join("")}
      </div>`
    : `<div class="card muted">${LANG==="hi"?"Koi shortage signal nahi — staffing theek lag rahi hai.":"No shortage signals right now."}</div>`;
  });
}
function zoneDetail(zone){
  const rows = ADM.forecast.rows.filter(r=>r.zone===zone);
  const trades = {};
  for(const r of rows){ trades[r.trade]=(trades[r.trade]||0)+r.predicted; }
  modal(`<h3 style="margin-bottom:12px">${esc(zone)} — ${LANG==="hi"?"7-दिन कुल":"7-day totals"}</h3>
    ${Object.entries(trades).sort((a,b)=>b[1]-a[1]).map(([tr,v])=>
      `<div class="kv"><span>${esc(tr)}</span><b>~${v.toFixed(1)} ${LANG==="hi"?"काम":"jobs"}</b></div>`).join("")}`);
}
