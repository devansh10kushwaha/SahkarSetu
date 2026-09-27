/* Customer "My Bookings" + Worker Hub views */
async function renderMyBookings(){
  const v = document.getElementById("view");
  const d = await API.get("/api/bookings/mine");
  const groups = {live:[], done:[], cancelled:[]};
  for(const b of d.bookings){
    if(["requested","accepted","enroute","in_progress"].includes(b.status)) groups.live.push(b);
    else if(b.status==="completed") groups.done.push(b);
    else groups.cancelled.push(b);
  }
  v.innerHTML = `
  <div class="wrap" style="padding-top:28px;max-width:860px">
    <div class="page-title">
      <h1>${LANG==="hi"?"मेरी बुकिंग":"My Bookings"}</h1>
      <button class="btn sm" onclick="go('browse')">+ ${LANG==="hi"?"नई बुकिंग":"New booking"}</button>
    </div>
    ${groups.live.length?`<h3 style="margin-bottom:10px">${LANG==="hi"?"चालू काम":"Live jobs"} (${groups.live.length})</h3>`+
      groups.live.map(b=>bookingCard(b,true)).join(""):""}
    <h3 style="margin:18px 0 10px">${LANG==="hi"?"पिछले काम":"Past jobs"}</h3>
    ${groups.done.map(b=>bookingCard(b,false)).join("") || `<p class="muted">${LANG==="hi"?"अभी कोई काम नहीं":"Nothing yet"}</p>`}
  </div>`;
}

/* Human words for the booking activity log. The customer should never have to guess
   why a booking changed hands or vanished - every line is written by the backend. */
const EV_TXT = {
  created:      {hi:"बुकिंग बनाई", en:"Booking placed"},
  chosen:       {hi:"आपने चुना", en:"You chose"},
  matched:      {hi:"नज़दीकी worker मिला", en:"Matched"},
  declined:     {hi:"ने मना किया", en:"declined"},
  redispatched: {hi:"आगे भेजा", en:"re-sent to"},
  no_worker:    {hi:"कोई free worker नहीं मिला", en:"no free worker left"},
  accepted:     {hi:"ने काम लिया", en:"accepted"},
  enroute:      {hi:"रास्ते में", en:"on the way"},
  in_progress:  {hi:"काम शुरू", en:"work started"},
  completed:    {hi:"काम पूरा", en:"completed"},
  paid:         {hi:"भुगतान हुआ", en:"paid"},
  reviewed:     {hi:"रेटिंग दी", en:"rated"},
  cancelled:    {hi:"रद्द किया", en:"cancelled"},
  expired:      {hi:"समय पर कोई accept नहीं किया", en:"expired - nobody accepted"},
};

function evKind(e){
  return esc(EV_TXT[e.kind] ? (LANG==="hi"?EV_TXT[e.kind].hi:EV_TXT[e.kind].en) : e.kind);
}
function evText(e){
  const t = EV_TXT[e.kind] ? (LANG==="hi"?EV_TXT[e.kind].hi:EV_TXT[e.kind].en) : e.kind;
  return `${t}${e.detail?" "+esc(e.detail):""}${e.actor&&e.kind!=="matched"&&e.kind!=="chosen"?" · "+esc(e.actor):""}${e.at_ist?" · "+e.at_ist:""}`;
}

function bookingCard(b, live){
  const STEPS = ["requested","accepted","enroute","in_progress","completed"];
  const idx = STEPS.indexOf(b.status);
  const stepper = live ? `<div class="stepper ${b.status==="cancelled"?"cancelled":""}">
      ${STEPS.slice(0,4).map((s,i)=>`<div class="step-pill ${i<idx?"done":i===idx?"now":""}">${stLabel(s)}</div>`).join("")}
    </div>` : "";
  return `<div class="card">
    <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
      <div>
        <b>${esc(b.service)}</b> <span class="muted small">#${esc(b.code)}</span>
        ${b.is_emergency?'<span class="badge red">'+ic("bolt",12)+' '+(LANG==="hi"?"इमरजेंसी":"Emergency")+"</span>":""}
        <div class="muted small">${esc(b.wname||"—")} · ${esc(b.coop||"")} · ${fmtDT(b.scheduled_for)}</div>
        <div class="muted small">${ic("pin",13)} ${esc(b.address)}</div>
      </div>
      <div style="text-align:right">
        <div class="price-tag"><span class="p">${rupees(b.price)}</span></div>
        <span class="badge ${b.payment_status==="paid"?"green":"amber"}">${b.payment_status==="paid"?(LANG==="hi"?"भुगतान हुआ":"Paid"):(LANG==="hi"?"बाकी":"Pending")}</span>
      </div>
    </div>
    ${stepper}
    ${(b.events&&b.events.length)?`<div class="muted small" style="margin-top:8px;line-height:1.55;border-left:2px solid var(--line);padding-left:9px">
      ${b.events.slice(0,3).map(e=>esc("• ")+evText(e)).join("<br>")}
      ${b.events.length>3?`<br><span style="opacity:.75">+ ${b.events.length-3} ${LANG==="hi"?"और":"more"}</span>`:""}
    </div>`:""}
    <div style="display:flex;gap:9px;margin-top:6px;flex-wrap:wrap" id="acts-${b.id}">${actionsFor(b,live)}</div>
  </div>`;
}

function actionsFor(b, live){
  let h = "";
  if(live){
    if(b.status==="requested")
      h += `<button class="btn sm danger" onclick="cancelBooking(${b.id})">${LANG==="hi"?"रद्द करें":"Cancel"}</button>`;
  } else {
    if(b.status==="completed"){
      if(b.payment_status!=="paid")
        h += `<button class="btn sm" onclick="payBooking(${b.id})">${LANG==="hi"?"भुगतान करें (demo)":"Pay now (demo)"}</button>`;
      else {
        h += `<a class="btn sm ghost" href="/api/bookings/${b.id}/invoice.pdf?t=${API.token}" target="_blank">${ic("receipt",13)} ${LANG==="hi"?"इनवॉइस":"Invoice"}</a>`;
        h += `<button class="btn sm ghost" onclick="openReview(${b.id})">${LANG==="hi"?"रेटिंग दें":"Rate"} ${ic("star",13)}</button>`;
      }
    }
  }
  h += `<button class="btn sm ghost" onclick="openDetail(${b.id})">${LANG==="hi"?"पूरी जानकारी":"Details"}</button>`;
  return h;
}

async function cancelBooking(id){
  if(!confirm(LANG==="hi"?"रद्द करना है?":"Cancel this booking?")) return;
  try{ await API.post(`/api/bookings/${id}/cancel`); toast(LANG==="hi"?"रद्द हुआ":"Cancelled"); renderMyBookings(); }
  catch(e){ toast(e.message); }
}
async function payBooking(id){
  try{
    const r = await API.post(`/api/bookings/${id}/pay`);
    modal(`<h2 style="margin-bottom:12px">${LANG==="hi"?"Demo Payment successful":"Demo payment successful"}</h2>
      <div class="kv"><span>${LANG==="hi"?"कुल":"Total"}</span><b>${rupees(r.amount)}</b></div>
      <div class="kv"><span>${LANG==="hi"?"platform fee (10%)":"Platform fee (10%)"}</span><b>- ${rupees(r.commission)}</b></div>
      <div class="kv"><span>${LANG==="hi"?"मिस्त्री को मिला":"Worker receives"}</span><b style="color:var(--green-dark)">${rupees(r.worker_gets)}</b></div>
      <div class="kv"><span>Ref</span><b class="small">${r.demo_gateway_ref}</b></div>
      <p class="muted small" style="margin-top:12px">${r.note}</p>
      <button class="btn big" style="width:100%;margin-top:14px" onclick="closeModal();renderMyBookings()">${LANG==="hi"?"ठीक है":"Done"}</button>`);
    renderMyBookings();
  }catch(e){ toast(e.message); }
}
function openReview(id){
  modal(`<h2 style="margin-bottom:14px">${LANG==="hi"?"कैसा रहा काम?":"How was the job?"}</h2>
    <div id="rv-err"></div>
    <div class="field"><label>${LANG==="hi"?"रेटिंग":"Rating"}</label>
      <select id="rv-rating"><option value="5">★★★★★</option><option value="4">★★★★</option><option value="3">★★★</option></select></div>
    <div class="field"><label>${LANG==="hi"?"टिप्पणी (वैकल्पिक)":"Comment (optional)"}</label><textarea id="rv-comment" rows="2"></textarea></div>
    <button class="btn big" style="width:100%" onclick="submitReview(${id})">${LANG==="hi"?"भेजें":"Submit"}</button>`);
}
async function submitReview(id){
  try{
    await API.post(`/api/bookings/${id}/review`, {rating:+val("rv-rating"), comment:val("rv-comment")});
    closeModal(); toast(LANG==="hi"?"धन्यवाद!":"Thanks!"); renderMyBookings();
  }catch(e){ document.getElementById("rv-err").innerHTML=`<div class="form-error">${esc(e.message)}</div>`; }
}
async function openDetail(id){
  const d = await API.get(`/api/bookings/${id}`);
  const b = d.booking;
  modal(`<h2 style="margin-bottom:12px">${esc(b.service)} · #${esc(b.code)}</h2>
    <div class="kv"><span>Status</span><b>${stLabel(b.status)}</b></div>
    <div class="kv"><span>${LANG==="hi"?"मिस्त्री":"Worker"}</span><b>${esc(b.wname||"-")} (${esc(b.coop||"")})</b></div>
    <div class="kv"><span>${LANG==="hi"?"ग्राहक":"Customer"}</span><b>${esc(b.cust_name)}</b></div>
    <div class="kv"><span>${LANG==="hi"?"रेट रेंज":"Rate range"}</span><b>₹${b.pmin}–₹${b.pmax}</b></div>
    ${b.payment?`<div class="kv"><span>Paid</span><b>${rupees(b.payment.amount)} → ${LANG==="hi"?"मिस्त्री को":"worker gets"} ${rupees(b.payment.net)}</b></div>`:""}
    ${b.review?`<div class="kv"><span>Review</span><b style="color:var(--amber)">${b.review.rating} ${ic("star",12)}</b></div>`:""}`);
}

/* ---------------- WORKER HUB ---------------- */
async function renderWorker(){
  const v = document.getElementById("view");
  const d = await API.get("/api/w/home");
  const w = d.worker;
  const verified = w.status === "verified";
  v.innerHTML = `
  <div class="wrap" style="padding-top:28px;max-width:900px">
    <div class="page-title">
      <div style="display:flex;gap:14px;align-items:center">
        <img class="avatar" src="${w.photo||"/static/img/w1.jpg"}">
        <div>
          <h1 style="font-size:22px">${esc(w.name)}</h1>
          <span class="muted small">${esc(d.coop.name)} · ${w.exp_years} ${LANG==="hi"?"साल अनुभव":"yrs exp"} ·
            <span class="badge ${d.skill_level==="expert"?"green":d.skill_level==="skilled"?"blue":"amber"}">${skillLabel(d.skill_level)}</span></span>
        </div>
        ${verified?'<span class="badge green"><span class="dot"></span>'+(LANG==="hi"?"प्रमाणित":"Verified")+"</span>"
                  :'<span class="badge amber">'+(LANG==="hi"?"verification pending":"Verification pending")+"</span>"}
      </div>
    </div>

    ${!verified?`<div class="card" style="border-left:4px solid var(--amber)">
      <b>${LANG==="hi"?"आपकी verification चल रही है":"Verification in progress"}</b>
      <p class="muted small">${LANG==="hi"?"Cooperative admin aapke documents check kar rahe hain. Verified hone ke baad hi aapko kaam dikhega.":'The cooperative is checking your papers. You will see jobs once verified.'}</p></div>`:""}

    <div class="stats-band" style="grid-template-columns:repeat(3,1fr);padding-top:0">
      <div class="stat-card"><div class="num">${rupees(d.earnings.week)}</div><div class="lbl">${LANG==="hi"?"इस हफ़्ते की कमाई":"This week"}</div></div>
      <div class="stat-card"><div class="num">${rupees(d.earnings.month)}</div><div class="lbl">${LANG==="hi"?"इस महीने":"This month"}</div></div>
      <div class="stat-card"><div class="num">${w.jobs_done}</div><div class="lbl">${LANG==="hi"?"कुल काम पूरे":"Jobs done (lifetime)"}</div></div>
    </div>

    <h3 style="margin:20px 0 10px">${LANG==="hi"?"आने वाले काम":"Upcoming jobs"} (${d.jobs.length})</h3>
    ${d.jobs.length ? d.jobs.map(j=>`
      <div class="card">
        <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px">
          <div>
            <b>${esc(j.service)}</b> ${j.is_emergency?'<span class="badge red">'+ic("bolt",12)+'</span>':""}
            <div class="muted small">${fmtDT(j.scheduled_for)} · ${ic("pin",13)} ${esc(j.address)} (${j.zone})</div>
            <div class="muted small">${LANG==="hi"?"ग्राहक":"Customer"}: ${esc(j.cust)} · ${j.cust_phone}</div>
          </div>
          <div style="text-align:right">
            <div class="price-tag"><span class="p">${rupees(j.price)}</span>
              <div class="muted tiny small">${LANG==="hi"?"आपको ~90% मिलेगा":"you get ~90%"}</div></div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:12px;align-items:center">
          <span class="badge blue">${stLabel(j.status)}</span>
          ${jobNextButton(j)}
          ${j.status==="requested"?`<button class="btn sm ghost" onclick="declineJob(${j.id})">${LANG==="hi"?"मना करें":"Decline"}</button>`:""}
        </div>
      </div>`).join("")
      : `<p class="muted card">${verified?(LANG==="hi"?"Abhi koi naya kaam nahi. Naye customers map par aapko dikh rahe hain.":"No new jobs right now."):(LANG==="hi"?"Verification ke baad kaam aayenge.":"Jobs arrive after verification.")}</p>`}

    <h3 style="margin:22px 0 10px">${LANG==="hi"?"कमाई का इतिहास":"Earnings history"}</h3>
    <div class="card" style="padding:8px 18px">
      <table class="tbl"><tr><th>${LANG==="hi"?"काम":"Job"}</th><th>${LANG==="hi"?"तारीख़":"Date"}</th><th>${LANG==="hi"?"रेट":"Rate"}</th><th>−10%</th><th>${LANG==="hi"?"मिला":"Got"}</th></tr>
      ${d.history.filter(h=>h.my_net).slice(0,10).map(h=>`
        <tr><td>${esc(h.service)}</td><td class="muted">${fmtDT(h.completed_at)}</td>
        <td>${rupees(h.my_net + h.commission)}</td><td class="muted">-${rupees(h.commission)}</td>
        <td><b style="color:var(--green-dark)">${rupees(h.my_net)}</b></td></tr>`).join("") ||
        '<tr><td colspan="5" class="muted">'+(LANG==="hi"?"अभी कोई कमाई नहीं":"No earnings yet")+'</td></tr>'}
      </table>
    </div>

    <h3 style="margin:22px 0 10px">${LANG==="hi"?"मेरे प्रमाणपत्र":"My certificates"}</h3>
    <div class="card" style="padding:14px 18px">
      ${d.certifications.length ? d.certifications.map(c=>`
        <div class="kv"><span>${ic("award",12)} <b>${esc(c.title)}</b>
          <span class="muted small">${esc(c.issuer||"")} ${c.year||""}</span></span>
          <b><span class="badge ${c.status==="verified"?"green":c.status==="rejected"?"red":"amber"}">${
            c.status==="verified"?(LANG==="hi"?"verified":"verified")
            :c.status==="rejected"?(LANG==="hi"?"नामंज़ूर":"rejected")
            :(LANG==="hi"?"जाँच बाकी":"pending")}</span></b></div>`).join("")
      : `<p class="muted small">${LANG==="hi"?"अभी कोई प्रमाणपत्र नहीं — ITI/NCVT सर्टिफिकेट जोड़ें।":"No certificates yet — add your ITI/NCVT ones."}</p>`}
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        <input id="wc-title" placeholder="${LANG==="hi"?"प्रमाणपत्र का नाम":"Certificate name"}" style="flex:2;min-width:150px">
        <input id="wc-issuer" placeholder="${LANG==="hi"?"जारीकर्ता (NCVT/Skill India)":"Issuer"}" style="flex:2;min-width:120px">
        <input id="wc-year" type="number" min="1970" max="2026" value="2024" style="width:88px">
        <button class="btn sm" onclick="addCert()">${LANG==="hi"?"+ जोड़ें":"+ Add"}</button>
      </div>
      <p class="muted tiny small" style="margin-top:6px">${LANG==="hi"?"समिति की जाँच के बाद ही badge मिलता है।":"The cooperative verifies it before it counts."}</p>
    </div>

    <h3 style="margin:22px 0 10px">${LANG==="hi"?"मेरी सुरक्षा (welfare)":"My welfare cover"}</h3>
    <div class="card-grid two">
      ${["PMSBY","PMJJBY"].map(sch=>{
        const row = (d.welfare||[]).find(x=>x.scheme===sch);
        const st = row ? row.status : null;
        const note = sch==="PMSBY"
          ? (LANG==="hi"?"₹20/साल → ₹2 लाख accident कवर":"Rs 20/year -> Rs 2 lakh accident cover")
          : (LANG==="hi"?"₹436/साल → ₹2 लाख जीवन बीमा":"Rs 436/year -> Rs 2 lakh life cover");
        let state = "";
        if(st==="active") state = `<span class="badge green">${LANG==="hi"?"सक्रिय":"Active"} ${row.valid_till||""}</span>
            <button class="btn sm ghost" style="margin-left:8px" onclick="openClaim('${sch}')">${LANG==="hi"?"क्लेम दर्ज करें":"File a claim"}</button>`;
        else if(st==="pending") state = `<span class="badge amber">${LANG==="hi"?"समिति की मंज़ूरी बाकी":"Awaiting society approval"}</span>`;
        else if(st==="rejected") state = `<span class="badge red">${LANG==="hi"?"नामंज़ूर":"Rejected"}</span>
            <button class="btn sm ghost" style="margin-left:8px" onclick="applyWelfare('${sch}')">${LANG==="hi"?"फिर आवेदन करें":"Apply again"}</button>`;
        else state = `<button class="btn sm" onclick="applyWelfare('${sch}')">${LANG==="hi"?"आवेदन करें":"Apply"}</button>`;
        return `<div class="card"><b>${ic("shield",14)} ${sch}</b>
          <p class="muted small">${note}</p>${state}</div>`;
      }).join("")}
    </div>
    ${(d.claims||[]).length ? `<div class="card" style="margin-top:10px">
      <h3>${LANG==="hi"?"मेरे क्लेम":"My claims"}</h3>
      ${d.claims.map(c=>`<div class="kv"><span>${ic("receipt",12)} ${esc(c.scheme)} — ${esc(c.reason||"")} ${c.amount?"· ₹"+c.amount:""}</span>
        <b><span class="badge ${c.status==="approved"?"green":c.status==="rejected"?"red":"amber"}">${c.status}</span></b></div>`).join("")}
    </div>` : ""}
  </div>`;
}

async function addCert(){
  const title = val("wc-title"), issuer = val("wc-issuer"), year = Number(val("wc-year") || 2024);
  if(!title || title.trim().length < 3){ toast(LANG==="hi"?"प्रमाणपत्र का नाम लिखें":"Enter a certificate name"); return; }
  try{ const r = await API.post("/api/w/certs", {title:title.trim(), issuer:issuer.trim(), year});
       toast(r.message || "OK"); renderWorker(); }
  catch(e){ toast(e.message); }
}
async function applyWelfare(scheme){
  try{ const r = await API.post("/api/w/welfare/apply", {scheme}); toast(r.message || scheme); renderWorker(); }
  catch(e){ toast(e.message); }
}
function openClaim(scheme){
  modal(`<h3>${LANG==="hi"?scheme+" क्लेम दर्ज करें":"File a "+scheme+" claim"}</h3>
    <div class="field"><label>${LANG==="hi"?"कारण":"Reason"}</label>
      <input id="cl-reason" placeholder="${LANG==="hi"?"क्या हुआ":"What happened"}"></div>
    <div class="field"><label>${LANG==="hi"?"राशि (₹)":"Amount (Rs)"}</label>
      <input id="cl-amount" type="number" min="0" max="200000" value="0"></div>
    <button class="btn" onclick="submitClaim('${scheme}')">${LANG==="hi"?"भेजें":"Submit"}</button>`);
}
async function submitClaim(scheme){
  try{ const r = await API.post("/api/w/welfare/claim",
        {scheme, reason:val("cl-reason"), amount:Number(val("cl-amount") || 0)});
       closeModal(); toast(r.message || "OK"); renderWorker(); }
  catch(e){ toast(e.message); }
}
const NEXT_LABEL = {
  requested: {hi:"काम स्वीकारें", en:"Accept job"},
  accepted:  {hi:"→ निकल चुका हूँ", en:"→ On my way"},
  enroute:   {hi:"▶ काम शुरू", en:"▶ Start work"},
  in_progress:{hi:"काम पूरा", en:"Mark complete"},
};
function jobNextButton(j){
  const nxt = NEXT_LABEL[j.status];
  if(!nxt) return "";
  return `<button class="btn sm" onclick="advanceJob(${j.id},'${ {requested:"accepted",accepted:"enroute",enroute:"in_progress",in_progress:"completed"}[j.status] }')">${nxt[LANG]}</button>`;
}
async function advanceJob(id, status){
  try{
    await API.post(`/api/w/jobs/${id}/status`, {status});
    toast(stLabel(status));
    renderWorker();
  }catch(e){ toast(e.message); }
}
async function declineJob(id){
  if(!confirm(LANG==="hi"?"Ye kaam manaa karna hai?":"Decline this job?")) return;
  try{
    const r = await API.post(`/api/w/jobs/${id}/decline`);
    toast(r.reassigned
      ? (LANG==="hi"?"Aapne mana kiya — ": "Declined — ") + r.reassigned.name + (LANG==="hi"?" ko bhej diya":" gets it")
      : (LANG==="hi"?"Booking cancel ho gayi (koi free worker nahi)":"Booking cancelled (no free worker)"));
    renderWorker();
  }catch(e){ toast(e.message); }
}
