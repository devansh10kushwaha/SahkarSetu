/* Cooperative Society dashboard — hard-scoped to the logged-in samiti.
   The PS names labour cooperative SOCIETIES as co-owners, so this view is what the
   samiti sees: its own workers, verifications, welfare decisions and earnings.
   The federation admin view (/api/a/*) is a superset; this one can never read
   another society's data (the backend scopes by users.coop_id). */
let SOC = {data:null};

async function renderSociety(){
  const v = document.getElementById("view");
  v.innerHTML = `<div class="app-main" id="soc-main"><p class="muted">Loading…</p></div>`;
  const el = document.getElementById("soc-main");
  try{
    SOC.data = await API.get("/api/c/home");
  }catch(e){
    el.innerHTML = `<div class="card form-error">${esc(e.message)}</div>`;
    return;
  }
  socPaint();
}

function socPaint(){
  const el = document.getElementById("soc-main");
  const d = SOC.data, c = d.coop, s = d.stats;
  const H = LANG==="hi";
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:14px">
      <div>
        <h1 style="font-size:22px;margin-bottom:4px">${esc(c.name)}</h1>
        <p class="muted small">${esc(c.fed||"")} · ${esc(c.zone)} ${H?"क्षेत्र":"zone"} ·
          <span class="badge blue">${H?"समिति डैशबोर्ड":"Society dashboard"}</span></p>
      </div>
      <div class="badge green" style="cursor:default">${ic("shield",12)} ${H?"केवल आपकी समिति का डेटा":"Only your society's data"}</div>
    </div>

    <div class="stats-band" style="grid-template-columns:repeat(4,1fr);padding-top:0">
      ${statCard(s.verified+" / "+s.workers, H?"verified कामगार":"verified workers")}
      ${statCard(s.live_jobs, H?"चालू काम":"live jobs")}
      ${statCard(s.jobs_today, H?"आज के काम":"jobs today")}
      ${statCard("₹"+Number(s.worker_net).toLocaleString("en-IN"), H?"कामगारों को मिला":"paid to workers")}
    </div>
    <div class="stats-band" style="grid-template-columns:repeat(4,1fr);padding-top:0;margin-bottom:16px">
      ${statCard(s.insured, H?"बीमित कामगार":"insured workers")}
      ${statCard(s.certs_pending, H?"प्रमाणपत्र जाँच बाकी":"certs to verify")}
      ${statCard(s.welfare_pending, H?"कल्याण आवेदन":"welfare requests")}
      ${statCard("₹"+Number(s.commission).toLocaleString("en-IN"), H?"समिति/प्लेटफ़ॉर्म फ़ीस":"platform fee (10%)")}
    </div>

    ${socVerifyQueue()}
    ${socCertQueue()}
    ${socWelfareQueue()}

    <div class="card-grid two" style="margin-top:6px">
      <div class="card"><h3>${H?"चालू काम":"Live jobs"} (${d.live.length})</h3>
        ${d.live.length ? d.live.map(j=>`
          <div class="kv"><span>${j.is_emergency?ic("bolt",12)+" ":""}${esc(j.service)} — ${esc(j.worker||"—")}
            <span class="muted small">· ${esc(j.cust||"")}</span></span>
            <b><span class="badge blue">${stLabel(j.status)}</span></b></div>`).join("")
          : `<p class="muted small">${H?"अभी कोई चालू काम नहीं":"No live jobs right now"}</p>`}
      </div>
      <div class="card"><h3>${H?"आपके क्षेत्र की डिमांड (अगले 7 दिन)":"Your zone's demand (next 7 days)"}</h3>
        ${Object.entries(d.zone_demand_7d||{}).filter(([,n])=>n>0).map(([tr,n])=>`
          <div class="kv"><span>${esc(tr)}</span><b>${n}</b></div>`).join("")
          || `<p class="muted small">${H?"अभी कोई अनुमानित डिमांड नहीं":"No forecast demand right now"}</p>`}
      </div>
    </div>

    <div class="card" style="padding:8px 18px;margin-top:14px;max-height:520px;overflow-y:auto">
      <h3 style="margin:10px 0">${H?"कामगार":"Workers"} (${d.workers.length})</h3>
      <table class="tbl"><tr><th>${H?"नाम":"Name"}</th><th>Kaam</th><th>${H?"कौशल":"Skill"}</th>
        <th>${H?"रेटिंग":"Rating"}</th><th>${H?"काम":"Jobs"}</th><th>${H?"कवर":"Cover"}</th></tr>
      ${d.workers.map(w=>`<tr>
        <td>${esc(w.name)} <span class="muted small">${esc(w.phone)}</span><br>
            <span class="badge ${w.status==="verified"?"green":w.status==="pending"?"amber":"red"}" style="margin-top:3px">${w.status}</span></td>
        <td class="muted small">${esc(w.trade)}</td>
        <td><span class="badge ${w.skill_level==="expert"?"green":w.skill_level==="skilled"?"blue":"amber"}">${skillLabel(w.skill_level)}</span>
            ${w.certs_verified?`<span class="muted small" title="${H?"सत्यापित प्रमाणपत्र":"verified certificates"}">${ic("award",11)} ${w.certs_verified} ${H?"प्रमाणपत्र":"certs"}</span>`:""}</td>
        <td>${w.rating_avg?stars(w.rating_avg):"—"}</td>
        <td>${w.jobs_done||0}</td>
        <td>${w.insured?'<span class="badge green">'+(H?"बीमित":"insured")+"</span>":'<span class="badge red">'+(H?"बिना कवर":"uncovered")+"</span>"}</td>
      </tr>`).join("")}
      </table>
    </div>

    <div class="card" style="margin-top:14px">
      <h3>${H?"हाल की गतिविधि":"Recent activity"}</h3>
      ${d.events.length ? d.events.map(e=>`
        <div class="kv"><span>${ic("activity",12)} <b>${evKind(e)}</b>
          <span class="muted small">${esc(e.detail||"")}${e.actor?" · "+esc(e.actor):""} · ${esc(e.code||"")}</span></span>
          <span class="muted small">${istTime(e.created_at)}</span></div>`).join("")
        : `<p class="muted small">—</p>`}
    </div>`;
}

function socVerifyQueue(){
  const H = LANG==="hi";
  const d = SOC.data;
  const pending = (d.workers||[]).filter(w=>w.status==="pending");
  if(!pending.length) return "";
  return `<div class="card" style="margin-top:14px">
    <h3>${ic("award",14)} ${H?"वेरिफिकेशन क़तार":"Verification queue"} (${pending.length})</h3>
    ${pending.map(w=>`
      <div class="kv" style="align-items:center">
        <span><b>${esc(w.name)}</b> <span class="muted small">${esc(w.trade)} · ${w.exp_years} ${H?"साल":"yrs"} · UAN ${esc(w.e_shram_uan||"—")}</span></span>
        <span style="white-space:nowrap">
          <button class="btn sm" onclick="socVerify(${w.id},true)">${ic("check",12)} ${H?"मंज़ूर":"Approve"}</button>
          <button class="btn sm danger" onclick="socVerify(${w.id},false)">${H?"नामंज़ूर":"Reject"}</button>
        </span></div>`).join("")}
  </div>`;
}

function socCertQueue(){
  const H = LANG==="hi";
  const certs = SOC.data.pending_certs||[];
  if(!certs.length) return "";
  return `<div class="card" style="margin-top:14px">
    <h3>${ic("award",14)} ${H?"प्रमाणपत्र जाँच":"Certificates to verify"} (${certs.length})</h3>
    ${certs.map(c=>`
      <div class="kv" style="align-items:center">
        <span>${ic("award",12)} <b>${esc(c.title)}</b>
          <span class="muted small">${esc(c.issuer||"")} ${c.year||""} · ${esc(c.name)}</span></span>
        <span style="white-space:nowrap">
          <button class="btn sm" onclick="socCert(${c.id},true)">${ic("check",12)} ${H?"मंज़ूर":"Verify"}</button>
          <button class="btn sm danger" onclick="socCert(${c.id},false)">${H?"नामंज़ूर":"Reject"}</button>
        </span></div>`).join("")}
  </div>`;
}

function socWelfareQueue(){
  const H = LANG==="hi";
  const d = SOC.data;
  const reqs = d.welfare_requests||[], claims = d.claims||[];
  if(!reqs.length && !claims.length) return "";
  return `<div class="card" style="margin-top:14px">
    <h3>${ic("shield",14)} ${H?"कल्याण आवेदन":"Welfare decisions"}</h3>
    ${reqs.map(r=>`
      <div class="kv" style="align-items:center">
        <span>${ic("shield",12)} <b>${esc(r.name)}</b> — ${esc(r.scheme)}
          <span class="muted small">(${H?"कामगार द्वारा आवेदन":"worker application"})</span></span>
        <span style="white-space:nowrap">
          <button class="btn sm" onclick="socWelfareDecide(${r.worker_id},'${r.scheme}',true)">${H?"मंज़ूर":"Approve"}</button>
          <button class="btn sm danger" onclick="socWelfareDecide(${r.worker_id},'${r.scheme}',false)">${H?"नामंज़ूर":"Reject"}</button>
        </span></div>`).join("")}
    ${claims.map(c=>`
      <div class="kv" style="align-items:center">
        <span>${ic("receipt",12)} <b>${esc(c.name)}</b> — ${esc(c.scheme)} ${H?"क्लेम":"claim"}
          <span class="muted small">${esc(c.reason||"")} · ₹${c.amount||0}</span></span>
        <span style="white-space:nowrap">
          <button class="btn sm" onclick="socClaimDecide(${c.id},true)">${H?"मंज़ूर":"Approve"}</button>
          <button class="btn sm danger" onclick="socClaimDecide(${c.id},false)">${H?"नामंज़ूर":"Reject"}</button>
        </span></div>`).join("")}
  </div>`;
}

async function socVerify(wid, approve){
  try{ await API.post(`/api/c/verify/${wid}`, {approve});
       toast(approve?(LANG==="hi"?"Verified":"Verified"):(LANG==="hi"?"नामंज़ूर":"Rejected"));
       await renderSociety(); }
  catch(e){ toast(e.message); }
}
async function socCert(cid, approve){
  try{ await API.post(`/api/c/certs/${cid}`, {approve});
       toast(approve?(LANG==="hi"?"प्रमाणपत्र verified":"Certificate verified"):(LANG==="hi"?"नामंज़ूर":"Rejected"));
       await renderSociety(); }
  catch(e){ toast(e.message); }
}
async function socWelfareDecide(wid, scheme, approve){
  try{ await API.post("/api/c/welfare/decide", {worker_id:wid, scheme, approve});
       toast(scheme+" "+(approve?(LANG==="hi"?"मंज़ूर":"approved"):(LANG==="hi"?"नामंज़ूर":"rejected")));
       await renderSociety(); }
  catch(e){ toast(e.message); }
}
async function socClaimDecide(cid, approve){
  try{ await API.post(`/api/c/welfare/claim/${cid}`, {approve});
       toast(LANG==="hi"?"क्लेम अपडेट हुआ":"Claim updated");
       await renderSociety(); }
  catch(e){ toast(e.message); }
}

function skillLabel(lvl){
  const H = LANG==="hi";
  return {expert: H?"विशेषज्ञ":"expert", skilled: H?"कुशल":"skilled", helper: H?"सहायक":"helper"}[lvl] || lvl || "—";
}
function istTime(ts){
  if(!ts) return "";
  const d = new Date(ts.replace(" ", "T") + "Z");   // DB stores UTC
  return d.toLocaleString("en-IN", {timeZone:"Asia/Kolkata", day:"2-digit", month:"short",
                                    hour:"2-digit", minute:"2-digit"});
}
