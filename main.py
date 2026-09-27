"""SahkarSetu - Cooperative Gig Services Platform (SIH26089 build).
FastAPI backend + static frontend host. Port 3001 (override with SAHKARSETU_PORT).
DEMO: payments are a labelled mock gateway; no real money moves.
"""
import os, sqlite3, math, io, csv as _csv, secrets, re as _re, threading, time as _time, asyncio
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import jwt as pyjwt
from db import (init_db, get_db, DB_LOCK, hash_pw, verify_pw, dummy_verify, JWT_SECRET,
                COMMISSION_PCT, TRADES, ZONES)
from forecast import compute_forecast, forecast_summary

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("SAHKARSETU_PORT", "3001"))
MAX_BODY_BYTES = 64 * 1024   # every endpoint here takes small JSON; anything bigger is abuse

app = FastAPI(title="SahkarSetu", docs_url=None, redoc_url=None)

@asynccontextmanager
async def _lifespan(_app):
    """Start the stale-offer sweeper with the server and stop it cleanly on shutdown."""
    task = asyncio.create_task(_expiry_loop())
    try:
        yield
    finally:
        task.cancel()

app.router.lifespan_context = _lifespan

# Bootstrap at import time so `uvicorn main:app` works on a fresh clone
# (the old build only seeded under `python main.py`).
if init_db():
    print("[sahkarsetu] fresh database seeded")
else:
    print("[sahkarsetu] database ready")

# --- perf: gzip responses (JS/CSS/JSON shrink ~3-4x) ---
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)

# ---------------------------------------------------------------- security headers
@app.middleware("http")
async def security_headers(request, call_next):
    # cheap body-size gate before any parsing happens
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_BODY_BYTES:
        return JSONResponse({"detail": "Payload too large"}, status_code=413)
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "geolocation=(self)")
    h.setdefault("Content-Security-Policy",
                 "default-src 'self'; img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
                 "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                 "connect-src 'self' https://nominatim.openstreetmap.org; "
                 "font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    return resp

# ---------------------------------------------------------------- auth helpers
def new_token(uid: int) -> str:
    return pyjwt.encode({"uid": uid, "exp": datetime.utcnow() + timedelta(days=30)},
                        JWT_SECRET, algorithm="HS256")

def _decode_user(request: Request, allow_query_token: bool = False):
    auth = request.headers.get("Authorization", "")
    tok = auth[7:] if auth.startswith("Bearer ") else None
    if not tok and allow_query_token:
        tok = request.query_params.get("t")
    if not tok:
        raise HTTPException(401, "Not logged in")
    try:
        payload = pyjwt.decode(tok, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "Session expired, login again")
    u = q("SELECT * FROM users WHERE id=?", (payload["uid"],), one=True)
    if not u:
        raise HTTPException(401, "User not found")
    return dict(u)

def get_current_user(request: Request):
    return _decode_user(request)

def get_current_user_download(request: Request):
    """Header token OR ?t=<token>. Only browser-download endpoints use this:
    <a href> links cannot set headers. Tokens in URLs leak into browser history /
    shared links / server logs, so everywhere else stays header-only."""
    return _decode_user(request, allow_query_token=True)

def require_role(*roles):
    def dep(u=Depends(get_current_user)):
        if u["role"] not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return u
    return dep

def q(sql, args=(), one=False):
    with DB_LOCK:
        conn = get_db()
        rows = conn.execute(sql, args).fetchall()
        return (rows[0] if rows else None) if one else rows

def ex(sql, args=()):
    with DB_LOCK:
        conn = get_db()
        cur = conn.execute(sql, args)
        conn.commit()
        lid = cur.lastrowid
        return lid

@contextmanager
def tx():
    """Atomic multi-statement write. Same shared connection + lock as q()/ex(),
    but one commit for the whole block so half-applied states cannot persist."""
    with DB_LOCK:
        conn = get_db()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

def ev(bid, kind, detail="", actor=""):
    """Append one line to a booking's activity log.

    The log is what the customer actually reads ("your chosen worker declined, so we
    sent it to X"), so every state change writes here. Best-effort by design: a
    logging failure must never break the booking it is describing."""
    try:
        ex("INSERT INTO booking_events(booking_id,kind,detail,actor) VALUES(?,?,?,?)",
           (bid, kind, detail[:160], actor[:80]))
    except Exception:
        pass

_IST = timezone(timedelta(hours=5, minutes=30))

def _ist_hm(ts):
    """SQLite datetime('now') strings are UTC - the app shows IST only."""
    try:
        return (datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                .astimezone(_IST).strftime("%-I:%M %p").lower())
    except Exception:
        return ""

def events_for(booking_ids):
    """Events for many bookings in ONE query (the mine/ list used to be N+1 free)."""
    if not booking_ids:
        return {}
    marks = ",".join("?" * len(booking_ids))
    out = {}
    for r in q(f"""SELECT booking_id,kind,detail,actor,created_at FROM booking_events
                   WHERE booking_id IN ({marks}) ORDER BY id DESC LIMIT 400""", tuple(booking_ids)):
        out.setdefault(r["booking_id"], []).append(
            {"kind": r["kind"], "detail": r["detail"], "actor": r["actor"],
             "at_ist": _ist_hm(r["created_at"])})
    return out

def expire_stale_requests(verbose=False):
    """Auto-cancel 'requested' bookings nobody accepted in OFFER_EXPIRY_HOURS.

    Without this, an unaccepted request sat on the customer's screen as a live job
    for weeks (a real one sat there 26 days) and kept holding a worker. Returns the
    ids it expired so tests can assert on it."""
    cutoff = (datetime.utcnow() - timedelta(hours=OFFER_EXPIRY_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    rows = q("SELECT id FROM bookings WHERE status='requested' AND created_at < ?", (cutoff,))
    done = []
    for r in rows:
        with tx() as conn:
            cur = conn.execute("UPDATE bookings SET status='cancelled' WHERE id=? AND status='requested'",
                               (r["id"],))
            if cur.rowcount:
                done.append(r["id"])
        if r["id"] in done:
            ev(r["id"], "expired",
               f"{OFFER_EXPIRY_HOURS} ghante mein koi worker accept nahi kar paaya — booking auto-cancel")
    if verbose and done:
        print(f"[sahkarsetu] expiry sweep: cancelled {len(done)} stale request(s): {done}")
    return done

async def _expiry_loop(interval=600):
    """Background sweep: run once shortly after boot (cleans historical strays),
    then every `interval` seconds."""
    await asyncio.sleep(15)
    print(f"[sahkarsetu] stale-offer sweeper active (every {interval}s, TTL {OFFER_EXPIRY_HOURS}h)")
    while True:
        try:
            expire_stale_requests(verbose=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:                    # never let the sweeper die
            print("[sahkarsetu] expiry sweep error:", e)
        await asyncio.sleep(interval)

def haversine(lat1, lng1, lat2, lng2):
    R, p = 6371.0, math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2 +
         math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lng2-lng1)*p/2)**2)
    return 2*R*math.asin(math.sqrt(a))

def zone_center(zk):
    for z in ZONES:
        if z[0] == zk:
            return z[3], z[4]
    return ZONES[0][3], ZONES[0][4]

def public_user(u):
    out = {"id": u["id"], "name": u["name"], "role": u["role"], "phone": u["phone"],
           "language": u["preferred_language"]}
    # society admins carry their cooperative so the UI can title the dashboard
    if u["role"] == "coop_admin":
        try:
            cid = dict(u).get("coop_id")
        except (TypeError, ValueError):
            cid = None
        if cid:
            c = q("SELECT id, name, zone FROM cooperatives WHERE id=?", (cid,), one=True)
            if c:
                out["coop"] = dict(c)
    return out

# ---------------------------------------------------------------- models
# Field caps matter: without them a single client can push arbitrarily large
# strings into the DB (no ORM-level limits, and SQLite happily stores them).
class LoginIn(BaseModel):
    phone: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=1, max_length=128)

class RegisterCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    phone: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=6, max_length=128)
    language: str = Field(default="hi", max_length=8)

class WorkerApply(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    phone: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=6, max_length=128)
    trade: str = Field(max_length=40)
    coop_id: int = Field(ge=1, le=10_000)
    exp_years: int = Field(default=3, ge=0, le=60)
    cert_title: str = Field(default="", max_length=120)
    cert_issuer: str = Field(default="", max_length=120)

class BookingIn(BaseModel):
    service_id: int = Field(ge=1)
    scheduled_for: str = Field(max_length=32)
    address: str = Field(min_length=3, max_length=300)
    zone: str = Field(max_length=20)
    notes: str = Field(default="", max_length=1000)
    worker_id: Optional[int] = Field(default=None, ge=1)
    is_emergency: bool = False

class StatusIn(BaseModel):
    status: str = Field(max_length=20)

class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5); comment: str = Field(default="", max_length=500)

class VerifyIn(BaseModel):
    approve: bool

class WelfareIn(BaseModel):
    worker_id: int = Field(ge=1); scheme: str = Field(max_length=10)

class CertIn(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    issuer: str = Field(default="", max_length=80)
    year: int = Field(ge=1970, le=2100)

class DecideIn(BaseModel):
    approve: bool

class WelfareApplyIn(BaseModel):
    scheme: str = Field(max_length=10)

class WelfareDecideIn(BaseModel):
    worker_id: int = Field(ge=1); scheme: str = Field(max_length=10); approve: bool

class ClaimIn(BaseModel):
    scheme: str = Field(max_length=10)
    reason: str = Field(min_length=3, max_length=300)
    amount: int = Field(default=0, ge=0, le=200000)

class PayoutRunIn(BaseModel):
    period_start: str = Field(max_length=10); period_end: str = Field(max_length=10)
    confirm_duplicate: bool = False

def _valid_phone(p: str) -> bool:
    return bool(_re.fullmatch(r"[0-9+\-\s]{10,15}", (p or "").strip()))

# ---------------------------------------------------------------- auth API
LOGIN_FAILS = {}     # "phone:ip" -> [failed-attempt timestamps]
LOGIN_IP_FAILS = {}  # "ip"       -> [failed-attempt timestamps across all phones]
REGISTER_HITS = {}   # "ip"       -> [registration-attempt timestamps]
LIMIT_LOCK = threading.Lock()
LOGIN_WINDOW = 900        # 15 minutes
LOGIN_MAX_PER_KEY = 10    # per phone+ip
LOGIN_MAX_PER_IP = 40     # across all phones from one ip (blunts credential stuffing)
MAP_CAP = 5000            # hard memory bound under flood

def _prune(d, key, window):
    """Drop stale entries and empty keys (the old build kept empty keys forever,
    so a flood of unique phone numbers grew the dict without bound)."""
    now = _time.time()
    if len(d) > MAP_CAP:
        for k in sorted(d, key=lambda k: d[k][-1] if d[k] else 0)[:len(d) // 2]:
            d.pop(k, None)
    recent = [t for t in d.get(key, ()) if now - t < window]
    if recent:
        d[key] = recent
    else:
        d.pop(key, None)
    return recent

def _too_many_fails(phone, ip):
    with LIMIT_LOCK:
        a = _prune(LOGIN_FAILS, f"{phone}:{ip}", LOGIN_WINDOW)
        b = _prune(LOGIN_IP_FAILS, ip, LOGIN_WINDOW)
        return len(a) >= LOGIN_MAX_PER_KEY or len(b) >= LOGIN_MAX_PER_IP

def _record_fail(phone, ip):
    with LIMIT_LOCK:
        LOGIN_FAILS.setdefault(f"{phone}:{ip}", []).append(_time.time())
        LOGIN_IP_FAILS.setdefault(ip, []).append(_time.time())

def _clear_fails(phone, ip):
    with LIMIT_LOCK:
        LOGIN_FAILS.pop(f"{phone}:{ip}", None)

def _register_flooded(ip):
    """Max 5 registration attempts per IP per hour (blocks directory flooding)."""
    with LIMIT_LOCK:
        return len(_prune(REGISTER_HITS, ip, 3600)) >= 5

def _register_hit(ip):
    with LIMIT_LOCK:
        REGISTER_HITS.setdefault(ip, []).append(_time.time())

def _is_local(ip):
    """Loopback/LAN clients are trusted (local QA runs); public IPs are limited.
    NOTE: demo posture - a real deployment sits behind a proxy and must read the
    forwarded client IP, not request.client.host."""
    return (ip.startswith("127.") or ip == "::1" or ip.startswith("192.168.")
            or ip.startswith("10.") or ip.startswith("172.16.") or ip.startswith("172.17.")
            or ip.startswith("172.18.") or ip.startswith("172.19.") or ip.startswith("172.2")
            or ip.startswith("172.30.") or ip.startswith("172.31."))

@app.post("/api/login")
def login(b: LoginIn, request: Request = None):
    ip = request.client.host if request else "?"
    phone = b.phone.strip()
    if _too_many_fails(phone, ip):
        raise HTTPException(429, "Bahut galat koshishen. 15 minute baad try karein.")
    u = q("SELECT * FROM users WHERE phone=?", (phone,), one=True)
    if not u:
        dummy_verify(b.password)       # equal work for unknown numbers (no timing oracle)
        _record_fail(phone, ip)
        raise HTTPException(401, "Galat number ya password")
    ok, needs_upgrade = verify_pw(b.password, u["password_hash"])
    if not ok:
        _record_fail(phone, ip)
        raise HTTPException(401, "Galat number ya password")
    _clear_fails(phone, ip)
    if needs_upgrade:                  # legacy row -> transparent PBKDF2 upgrade
        ex("UPDATE users SET password_hash=? WHERE id=?", (hash_pw(b.password), u["id"]))
    return {"token": new_token(u["id"]), "user": public_user(u)}

@app.post("/api/register-customer")
def register_customer(b: RegisterCustomer, request: Request = None):
    ip = request.client.host if request else "?"
    if not _is_local(ip) and _register_flooded(ip):
        raise HTTPException(429, "Bahut zyada attempts. Thodi der baad koshish karein.")
    if not _valid_phone(b.phone):
        raise HTTPException(400, "Phone/password check karo")
    b.name = b.name.strip()[:60]
    if not _is_local(ip):
        _register_hit(ip)
    try:
        uid = ex("INSERT INTO users(phone,password_hash,name,role,preferred_language) VALUES(?,?,?,'customer',?)",
                 (b.phone.strip(), hash_pw(b.password), b.name.strip(), b.language))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ye number pehle se registered hai")
    return {"token": new_token(uid), "user": {"id": uid, "name": b.name, "role": "customer",
                                              "phone": b.phone, "language": b.language}}

@app.post("/api/apply-worker")
def apply_worker(b: WorkerApply, request: Request = None):
    ip = request.client.host if request else "?"
    if not _is_local(ip) and _register_flooded(ip):
        raise HTTPException(429, "Bahut zyada attempts. Thodi der baad koshish karein.")
    if not _valid_phone(b.phone):
        raise HTTPException(400, "Phone sirf digits hona chahiye (10-15)")
    if b.trade not in [t[0] for t in TRADES]:
        raise HTTPException(400, "Unknown trade")
    coop = q("SELECT * FROM cooperatives WHERE id=?", (b.coop_id,), one=True)
    if not coop:
        raise HTTPException(400, "Cooperative not found")
    if not _is_local(ip):
        _register_hit(ip)
    b.name = b.name.strip()[:60]
    lat, lng = zone_center(coop["zone"])
    try:
        with tx() as conn:
            cur = conn.execute(
                "INSERT INTO users(phone,password_hash,name,role,preferred_language) VALUES(?,?,?,'worker','hi')",
                (b.phone.strip(), hash_pw(b.password), b.name.strip()))
            uid = cur.lastrowid
            conn.execute("""INSERT INTO workers(user_id,coop_id,trade,exp_years,bio,status,zone,lat,lng,e_shram_uan,
                  hourly_min,hourly_max)
                  VALUES(?,?,?,?,?, 'pending', ?, ?, ?, ?, 200, 450)""",
                         (uid, b.coop_id, b.trade, b.exp_years,
                          f"{b.exp_years} saal ka tajurba", coop["zone"], lat, lng,
                          f"{b.phone[:4]}-{b.phone[4:8]}-{b.phone[8:]}"))
            if b.cert_title:
                conn.execute("INSERT INTO certifications(worker_id,title,issuer,year,verified_by_coop) VALUES(?,?,?,?,0)",
                             (uid, b.cert_title, b.cert_issuer or "Self-declared", date.today().year))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ye number pehle se registered hai")
    return {"token": new_token(uid),
            "user": {"id": uid, "name": b.name, "role": "worker", "phone": b.phone, "language": "hi"},
            "message": "Application submitted. Cooperative verification ke baad badge milega."}

@app.get("/api/me")
def me(u=Depends(get_current_user)):
    out = public_user(u)
    if u["role"] == "worker":
        w = q("SELECT * FROM workers WHERE user_id=?", (u["id"],), one=True)
        if w:
            out["worker"] = dict(w)
            out["worker"]["coop_name"] = q("SELECT name FROM cooperatives WHERE id=?",
                                           (w["coop_id"],), one=True)["name"]
    return out

# ---------------------------------------------------------------- catalog
@app.get("/api/catalog")
def catalog():
    trades = [{"key": t[0], "hi": t[1], "en": t[2]} for t in TRADES]
    svcs = q("SELECT * FROM services ORDER BY trade, name_en")
    by_trade = {}
    for s in svcs:
        by_trade.setdefault(s["trade"], []).append(dict(s))
    zones = [{"key": z[0], "en": z[1], "hi": z[2],
              "lat": z[3], "lng": z[4]} for z in ZONES]
    coops = [dict(r) for r in q("""SELECT c.id, c.name, c.zone, f.name fed FROM cooperatives c
                                   JOIN federations f ON f.id=c.federation_id""")]
    stats = {
        "workers": q("SELECT COUNT(*) n FROM workers WHERE status='verified'", one=True)["n"],
        "jobs": q("SELECT COUNT(*) n FROM bookings WHERE status='completed'", one=True)["n"],
        "coops": q("SELECT COUNT(*) n FROM cooperatives", one=True)["n"],
        "share": 100 - COMMISSION_PCT,
    }
    return {"trades": trades, "services_by_trade": by_trade, "zones": zones,
            "cooperatives": coops, "stats": stats}

@app.get("/api/workers")
def list_workers(trade: str = None, zone: str = None, s: str = None):
    sql = """SELECT w.user_id id, w.trade, w.zone, w.lat, w.lng, w.rating_avg, w.rating_count,
                    w.hourly_min, w.hourly_max, w.jobs_done, w.photo, w.exp_years, w.status,
                    u.name, c.name coop_name,
                    (SELECT COUNT(*) FROM certifications c2
                      WHERE c2.worker_id=w.user_id AND c2.status='verified') certs,
                    (SELECT GROUP_CONCAT(wf.scheme) FROM welfare wf
                      WHERE wf.worker_id=w.user_id AND wf.status='active') welfare
             FROM workers w JOIN users u ON u.id=w.user_id
             JOIN cooperatives c ON c.id=w.coop_id
             WHERE w.status='verified'"""
    args = []
    if trade:
        sql += " AND w.trade=?"; args.append(trade)
    if zone:
        sql += " AND w.zone=?"; args.append(zone)
    if s:
        sql += " AND u.name LIKE ?"; args.append(f"%{s}%")
    rows = [dict(r) for r in q(sql, args)]
    # availability in ONE extra query: the card must be able to show Busy before the
    # customer picks someone (picking a busy worker is a hard refusal now, not a reroute)
    busy = {r["worker_id"]: r["n"] for r in q("""SELECT worker_id, COUNT(*) n FROM bookings
             WHERE status IN ('accepted','enroute','in_progress') GROUP BY worker_id""")}
    for r in rows:
        r["avg_price"] = ((r["hourly_min"] or 0) + (r["hourly_max"] or 0)) // 2 or 250
        r["active_jobs"] = busy.get(r["id"], 0)
        r["busy"] = r["active_jobs"] > 0
        r["skill_level"] = _skill_of(r["exp_years"], r["certs"], r["rating_avg"], r["jobs_done"])
        r["insured"] = bool((r["welfare"] or "").strip())
        r["welfare_schemes"] = (r["welfare"] or "").split(",") if r["welfare"] else []
    return {"workers": rows}

@app.get("/api/workers/{wid}")
def worker_profile(wid: int):
    w = q("""SELECT w.*, u.name, u.phone, c.name coop_name, c.district
             FROM workers w JOIN users u ON u.id=w.user_id JOIN cooperatives c ON c.id=w.coop_id
             WHERE w.user_id=? AND w.status='verified'""", (wid,), one=True)
    if not w:
        raise HTTPException(404, "Worker not found")
    certs = [dict(r) for r in q("""SELECT id, title, issuer, year, status FROM certifications
                                   WHERE worker_id=? ORDER BY (status='verified') DESC, id""", (wid,))]
    reviews = [dict(r) for r in q("""SELECT r.rating, r.comment, r.created_at, u.name cust
                  FROM reviews r JOIN users u ON u.id=r.customer_id
                  WHERE r.worker_id=? AND r.comment != '' ORDER BY r.id DESC LIMIT 8""", (wid,))]
    welfare = [dict(r) for r in q("SELECT scheme, valid_till FROM welfare WHERE worker_id=? AND status='active'", (wid,))]
    svcs = [dict(r) for r in q("SELECT id, slug, name_en, name_hi, pmin, pmax, unit FROM services WHERE trade=?", (w["trade"],))]
    d = dict(w)
    d.pop("e_shram_uan", None)          # privacy: never expose UAN publicly
    d["phone"] = _mask_phone(d.get("phone"))   # privacy: mask the worker's number
    # the list endpoint (/api/workers) exposes the worker id as "id"; expose the same key
    # here so clients cannot silently lose it (a profile Book button reading w.id on a
    # user_id-only payload sent worker_id=null and the booking was auto-matched instead)
    d["id"] = d["user_id"]
    d["active_jobs"] = q("""SELECT COUNT(*) n FROM bookings WHERE worker_id=? AND
                            status IN ('accepted','enroute','in_progress')""", (wid,), one=True)["n"]
    d["busy"] = d["active_jobs"] > 0
    d["skill_level"] = _skill_of(d.get("exp_years"), sum(1 for c in certs if c["status"] == "verified"),
                                 d.get("rating_avg"), d.get("jobs_done"))
    d["jobs_today"] = q("""SELECT COUNT(*) n FROM bookings WHERE worker_id=? AND status='completed'
                           AND date(COALESCE(completed_at, scheduled_for))=date('now')""",
                        (wid,), one=True)["n"]
    d["insured"] = bool(welfare)
    d["welfare_schemes"] = [x["scheme"] for x in welfare]
    return {"worker": d, "certifications": certs, "reviews": reviews,
            "welfare": welfare, "services": svcs}

# ---------------------------------------------------------------- matching + booking
ACTIVE_STATES = ("requested", "accepted", "enroute", "in_progress")
# Offer policy for the matcher. A worker counts as committed only once he ACCEPTS;
# an unaccepted offer holds him for OFFER_HOLD_HOURS, and at most PENDING_OFFER_CAP
# live offers may sit on him at once. Without this, one ignored request benched him
# permanently (observed live: a 4-week-old unaccepted booking kept a worker out of
# every future match, so customers' bookings kept landing on somebody else).
# The cap is a flood guard only: the 2-hour hold already frees him, so it sits above
# the number of jobs a busy worker legitimately sees at once. Customer-picked workers
# are exempt - they are asked for by name.
OFFER_HOLD_HOURS = 2
PENDING_OFFER_CAP = 3
# A request nobody accepts within this window is auto-cancelled (with an event line the
# customer can read) instead of sitting on their screen as a "live job" for weeks.
OFFER_EXPIRY_HOURS = int(os.environ.get("SAHKARSETU_OFFER_EXPIRY_HOURS", "24"))
ZONE_KEYS = {z[0] for z in ZONES}

def _mask_phone(p):
    """Public profiles show 98******77, never the full number (privacy)."""
    p = str(p or "")
    return (p[:2] + "*" * max(0, len(p) - 4) + p[-2:]) if len(p) > 4 else "**"

def _skill_of(exp_years, n_certs, rating, jobs_done):
    """Explainable skill profile (PS clause: 'worker skill profiling and certification').
    Computed from experience + cooperative-VERIFIED certificates + customer rating, never
    stored, so it cannot drift away from the evidence behind it."""
    exp = exp_years or 0
    if exp >= 10 and ((n_certs or 0) >= 2 or (rating or 0) >= 4.5):
        return "expert"
    if exp >= 3 or (n_certs or 0) >= 1:
        return "skilled"
    return "helper"

def find_matches(service, zone_key, limit=3, exclude_ids=()):
    """Candidates for a service in a zone: the best FREE, verified workers of that trade.

    One query instead of the old per-candidate busy-check loop (that was N+1 on the
    hot booking path). A worker with committed work (accepted/enroute/in_progress) is
    never offered; fresh unaccepted offers hold him (see OFFER_HOLD_HOURS/PENDING_OFFER_CAP).

    Ranking (PS clause: 'AI-based demand forecasting and workforce allocation'):
    distance-weighted score, not distance alone - 0.9/km travelled, +0.35 per rating
    point (verified quality), -0.6 per job already finished today (work rotation, so
    the same two workers don't soak up every booking while others idle). Every pick
    carries a 'why' string the customer/admin can read - no black box."""
    zlat, zlng = zone_center(zone_key)
    ex_ids = tuple(exclude_ids or ())
    sql = """SELECT w.user_id id, w.lat, w.lng, w.zone, w.rating_avg, w.radius_km, w.jobs_done,
                    w.exp_years, u.name,
                    (SELECT COUNT(*) FROM certifications c
                      WHERE c.worker_id=w.user_id AND c.status='verified') certs,
                    (SELECT COUNT(*) FROM bookings j
                      WHERE j.worker_id=w.user_id AND j.status='completed'
                        AND date(COALESCE(j.completed_at, j.scheduled_for))=date('now')) jobs_today
             FROM workers w JOIN users u ON u.id=w.user_id
             WHERE w.trade=? AND w.status='verified'
               AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.worker_id=w.user_id
                               AND b.status IN ('accepted','enroute','in_progress'))
               AND (SELECT COUNT(*) FROM bookings p WHERE p.worker_id=w.user_id
                    AND p.status='requested' AND p.created_at >= datetime('now', ?)) < ?"""
    args = [service["trade"], f"-{OFFER_HOLD_HOURS} hours", PENDING_OFFER_CAP]
    if ex_ids:
        sql += " AND w.user_id NOT IN (%s)" % ",".join("?" * len(ex_ids))
        args.extend(ex_ids)
    rows = q(sql, args)
    in_zone, elsewhere = [], []
    for cw in rows:
        dist = haversine(zlat, zlng, cw["lat"], cw["lng"]) if cw["lat"] else 99.0
        rating = cw["rating_avg"] or 0
        jobs_today = cw["jobs_today"] or 0
        score = round(10.0 - 0.9 * dist + 0.35 * rating - 0.6 * jobs_today, 2)
        rec = {"id": cw["id"], "name": cw["name"], "rating": cw["rating_avg"],
               "jobs_done": cw["jobs_done"], "distance_km": round(dist, 1),
               "same_zone": cw["zone"] == zone_key, "jobs_today": jobs_today,
               "skill_level": _skill_of(cw["exp_years"], cw["certs"], rating, cw["jobs_done"]),
               "score": score,
               "why": f"{round(dist, 1)} km · ★{rating} · {jobs_today} jobs today"}
        # rank tuple: score desc, rating desc, fewest jobs done (rotation), then id for a
        # stable order. The dict is NEVER part of the tuple: equal scores used to fall
        # through to comparing dicts and crashed the booking path with a TypeError.
        entry = (-score, -rating, cw["jobs_done"] or 0, cw["id"], rec)
        if cw["zone"] == zone_key and dist <= max(cw["radius_km"] or 8, 10):
            in_zone.append(entry)
        else:
            # fallback tier: verified + free, same trade, elsewhere in Delhi
            elsewhere.append(entry)
    pool = sorted(in_zone or elsewhere, key=lambda e: e[:4])
    return [rec for *_, rec in pool[:limit]]

@app.post("/api/bookings")
def create_booking(b: BookingIn, u=Depends(require_role("customer"))):
    svc = q("SELECT * FROM services WHERE id=?", (b.service_id,), one=True)
    if not svc:
        raise HTTPException(404, "Service not found")
    if not b.address.strip():
        raise HTTPException(400, "Address required")
    zone = b.zone.strip().lower()
    if zone not in ZONE_KEYS:
        raise HTTPException(400, "Ye area list mein nahi hai — list se chunein")
    try:
        when = datetime.fromisoformat(b.scheduled_for)
    except ValueError:
        raise HTTPException(400, "Bad schedule time")
    now = datetime.now()
    if when < now - timedelta(minutes=30):
        raise HTTPException(400, "Purani tareekh ki booking nahi ho sakti — aage ka time chunein")
    if when > now + timedelta(days=90):
        raise HTTPException(400, "90 din se zyada aage ki booking nahi hoti")

    chosen = None
    was_chosen = False
    if b.worker_id:
        w = q("""SELECT w.user_id, u.name, c.name coop, w.rating_avg, w.lat, w.lng
                 FROM workers w JOIN users u ON u.id=w.user_id
                 JOIN cooperatives c ON c.id=w.coop_id
                 WHERE w.user_id=? AND w.status='verified'""", (b.worker_id,), one=True)
        if not w or q("SELECT trade FROM workers WHERE user_id=?", (b.worker_id,), one=True)["trade"] != svc["trade"]:
            raise HTTPException(400, "Worker not available for this service")
        if q("""SELECT 1 FROM bookings WHERE worker_id=? AND status IN
                ('accepted','enroute','in_progress') LIMIT 1""", (b.worker_id,), one=True):
            # Refusing is right (his choice is honoured, never silently rerouted), but the
            # customer gets a one-tap way forward: the nearest free worker of the same trade.
            alt = (find_matches(svc, zone, limit=1) or [None])[0]
            raise HTTPException(409, {"message": "Ye worker abhi ek kaam par hai — tab tak free nahi.",
                                      "busy": True, "alternative": alt})
        d = haversine(*zone_center(zone), w["lat"] or 0, w["lng"] or 0) if w["lat"] else None
        chosen = {"id": w["user_id"], "name": w["name"], "coop": w["coop"],
                  "distance_km": round(d, 1) if d is not None else None, "rating": w["rating_avg"]}
        was_chosen = True
    else:
        matches = find_matches(svc, zone, limit=1)
        if not matches:
            raise HTTPException(409, "Is area mein abhi koi worker free nahi hai. Thodi der baad try karein.")
        m = matches[0]
        wk = q("""SELECT c.name coop FROM workers w JOIN cooperatives c ON c.id=w.coop_id
                  WHERE w.user_id=?""", (m["id"],), one=True)
        chosen = {**m, "coop": wk["coop"] if wk else ""}

    price = (svc["pmin"] + svc["pmax"]) // 2 // 10 * 10
    code = f"SS{datetime.now().strftime('%y%m%d%H%M%S')}{u['id']:03d}{secrets.token_hex(2).upper()}"
    with tx() as conn:
        cur = conn.execute("""INSERT INTO bookings(code,customer_id,worker_id,service_id,scheduled_for,address,zone,
                    notes,is_emergency,status,price) VALUES(?,?,?,?,?,?,?,?,?,'requested',?)""",
                           (code, u["id"], chosen["id"], b.service_id, when.isoformat(), b.address.strip(),
                            zone, b.notes.strip(), 1 if b.is_emergency else 0, price))
        bid = cur.lastrowid
    ev(bid, "created", f"{svc['name_en']} · ₹{price}" + (" · emergency" if b.is_emergency else ""),
       actor=u["name"])
    ev(bid, "chosen" if was_chosen else "matched",
       f"{chosen['name']} — {chosen['distance_km']} km" if chosen.get("distance_km") is not None
       else chosen["name"], actor="customer" if was_chosen else "system")
    if was_chosen:
        note = "Your chosen worker"
    elif chosen.get("why"):
        note = f"Matched {svc['trade']} — {chosen['why']}"
    elif chosen.get("distance_km") is not None:
        note = f"Nearest free {svc['trade']} — {chosen['distance_km']} km away"
    else:
        note = f"Nearest free {svc['trade']}"
    return {"booking_id": bid, "code": code, "status": "requested", "price": price,
            "worker": chosen, "match_note": note}

@app.get("/api/bookings/mine")
def my_bookings(u=Depends(require_role("customer"))):
    rows = q("""SELECT b.*, s.name_en service, s.unit, w.user_id wid, wu.name wname, w.photo,
                       w.rating_avg wr, c.name coop, p.amount paid_amt, p.net worker_net, p.commission comm
                FROM bookings b
                JOIN services s ON s.id=b.service_id
                LEFT JOIN workers w ON w.user_id=b.worker_id
                LEFT JOIN users wu ON wu.id=w.user_id
                LEFT JOIN cooperatives c ON c.id=w.coop_id
                LEFT JOIN payments p ON p.booking_id=b.id
                WHERE b.customer_id=? ORDER BY b.id DESC LIMIT 60""", (u["id"],))
    out = [dict(r) for r in rows]
    evs = events_for([r["id"] for r in out])
    for r in out:
        r["events"] = evs.get(r["id"], [])[:8]
    return {"bookings": out}

@app.get("/api/bookings/{bid}")
def booking_detail(bid: int, u=Depends(get_current_user)):
    b = q("""SELECT b.*, s.name_en service, s.trade, s.pmin, s.pmax, s.unit,
                    wu.name wname, w.photo, w.rating_avg wr, w.exp_years, c.name coop,
                    cu.name cust_name, cu.phone cust_phone
             FROM bookings b JOIN services s ON s.id=b.service_id
             LEFT JOIN workers w ON w.user_id=b.worker_id
             LEFT JOIN users wu ON wu.id=w.user_id
             LEFT JOIN cooperatives c ON c.id=w.coop_id
             JOIN users cu ON cu.id=b.customer_id
             WHERE b.id=?""", (bid,), one=True)
    if not b:
        raise HTTPException(404, "Not found")
    allowed = u["id"] in (b["customer_id"], b["worker_id"]) or u["role"] in ("federation_admin", "super_admin")
    if not allowed:
        raise HTTPException(403, "Not your booking")
    rev = q("SELECT rating, comment FROM reviews WHERE booking_id=?", (bid,), one=True)
    pay = q("SELECT amount, commission, net, method, gateway_ref, paid_at FROM payments WHERE booking_id=?", (bid,), one=True)
    d = dict(b)
    d["review"] = dict(rev) if rev else None
    d["payment"] = dict(pay) if pay else None
    d["events"] = events_for([bid]).get(bid, [])[:20]
    return {"booking": d}

@app.post("/api/bookings/{bid}/cancel")
def cancel_booking(bid: int, u=Depends(require_role("customer"))):
    b = q("SELECT * FROM bookings WHERE id=? AND customer_id=?", (bid, u["id"]), one=True)
    if not b:
        raise HTTPException(404, "Not found")
    if b["status"] not in ("requested",):
        raise HTTPException(400, "Job already underway — cannot cancel now")
    ex("UPDATE bookings SET status='cancelled' WHERE id=?", (bid,))
    ev(bid, "cancelled", actor=u["name"])
    return {"ok": True, "status": "cancelled"}

@app.post("/api/bookings/{bid}/pay")
def pay_booking(bid: int, u=Depends(require_role("customer"))):
    b = q("SELECT * FROM bookings WHERE id=? AND customer_id=?", (bid, u["id"]), one=True)
    if not b:
        raise HTTPException(404, "Not found")
    if b["status"] != "completed":
        raise HTTPException(400, "Job complete hone ke baad hi payment hota hai")
    if b["payment_status"] == "paid":
        raise HTTPException(409, "Already paid")
    amount = b["price"]
    commission = int(amount * COMMISSION_PCT / 100)
    net = amount - commission
    ref = f"DEMOUPI{int(datetime.now().timestamp())}"
    with tx() as conn:
        conn.execute("INSERT INTO payments(booking_id,amount,commission,net,gateway_ref) VALUES(?,?,?,?,?)",
                     (bid, amount, commission, net, ref))
        conn.execute("UPDATE bookings SET payment_status='paid' WHERE id=?", (bid,))
    ev(bid, "paid", f"₹{amount} · worker ko ₹{net} · demo UPI {ref}")
    return {"ok": True, "demo_gateway_ref": ref, "amount": amount,
            "commission": commission, "commission_pct": COMMISSION_PCT,
            "worker_gets": net,
            "note": "DEMO MODE - no real money moved. Real build swaps in UPI/PG here."}

@app.post("/api/bookings/{bid}/review")
def review_booking(bid: int, br: ReviewIn, u=Depends(require_role("customer"))):
    b = q("SELECT * FROM bookings WHERE id=? AND customer_id=?", (bid, u["id"]), one=True)
    if not b:
        raise HTTPException(404, "Not found")
    if b["status"] != "completed":
        raise HTTPException(400, "Pehle kaam poora hone do")
    if q("SELECT 1 FROM reviews WHERE booking_id=?", (bid,), one=True):
        raise HTTPException(409, "Already reviewed")
    with tx() as conn:
        conn.execute("INSERT INTO reviews(booking_id,customer_id,worker_id,rating,comment) VALUES(?,?,?,?,?)",
                     (bid, u["id"], b["worker_id"], br.rating, br.comment.strip()))
        agg = conn.execute("SELECT ROUND(AVG(rating),1) a, COUNT(*) c FROM reviews WHERE worker_id=?",
                           (b["worker_id"],)).fetchone()
        conn.execute("UPDATE workers SET rating_avg=?, rating_count=? WHERE user_id=?",
                     (agg["a"], agg["c"], b["worker_id"]))
    ev(bid, "reviewed", f"{br.rating}★" + (f" · {br.comment.strip()[:60]}" if br.comment.strip() else ""))
    return {"ok": True}

# ---------------------------------------------------------------- invoices
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Helvetica silently prints boxes for Devanagari, so any non-Latin value switches
# to a Unicode face (GNU FreeFont ships with the base OS).
_UNI_FONT = None
_UNI_FONT_PATH = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"

def _unicode_font():
    global _UNI_FONT
    if _UNI_FONT is None:
        try:
            pdfmetrics.registerFont(TTFont("FreeSerif", _UNI_FONT_PATH))
            _UNI_FONT = "FreeSerif"
        except Exception:
            _UNI_FONT = ""
    return _UNI_FONT

_WINANSI_PUNCT = set("·—–’‘“”…•€°")   # fine in the base encoding; no need to switch fonts

def _needs_unicode(s: str) -> bool:
    return any(ord(ch) > 0xFF and ch not in _WINANSI_PUNCT for ch in s)

def make_invoice_pdf(b, pay) -> bytes:
    """Cursor-based layout from the top of the page.
    (The previous version reset the cursor to y=0 and drew the whole payment
    breakdown below the page edge - the printed invoice showed no 90/10 split.)"""
    buf = io.BytesIO()
    W, H = A4
    cv = canvas.Canvas(buf, pagesize=A4)
    GREEN = (0.13, 0.42, 0.28)
    uni = _unicode_font()

    def text(x, y, s, font="Helvetica", size=10.5, color=(0, 0, 0)):
        s = str(s if s is not None else "")
        use = font
        if uni and font.startswith("Helvetica") and _needs_unicode(s):
            use = uni
        cv.setFillColorRGB(*color)
        cv.setFont(use, size)
        cv.drawString(x, y, s)

    cv.setFillColorRGB(*GREEN)
    cv.rect(0, H - 30 * mm, W, 30 * mm, stroke=0, fill=1)
    cv.setFillColorRGB(1, 1, 1)
    cv.setFont("Helvetica-Bold", 24)
    cv.drawString(18 * mm, H - 16 * mm, "SahkarSetu")
    cv.setFont("Helvetica", 11)
    cv.drawString(18 * mm, H - 23 * mm, "Cooperative Gig Services  ·  Sahkar se Samriddhi")

    y = H - 45 * mm
    cv.setFillColorRGB(0, 0, 0)
    cv.setFont("Helvetica-Bold", 14)
    cv.drawString(18 * mm, y, f"Invoice — Booking {b['code']}")
    y -= 9 * mm
    details = [("Date", datetime.now().strftime("%d %b %Y %H:%M IST")),
               ("Customer", f"{b['cust_name']} ({b['cust_phone']})"),
               ("Worker", f"{b['wname']} — {b['coop']}"),
               ("Service", b["service"]),
               ("Address", b["address"]),
               ("Scheduled", str(b["scheduled_for"])[:16].replace("T", " "))]
    for k, v in details:
        text(18 * mm, y, k + ":", "Helvetica-Bold")
        text(50 * mm, y, str(v)[:70])
        y -= 6.5 * mm

    y -= 4 * mm
    cv.setStrokeColorRGB(0.75, 0.75, 0.75)
    cv.line(18 * mm, y, W - 18 * mm, y)
    y -= 10 * mm

    # the 90/10 split - the whole point of the invoice, always inside the page
    for label, val, bold in [(f"Job charge ({b['unit']})", f"Rs {pay['amount']}", False),
                             (f"SahkarSetu platform fee ({COMMISSION_PCT:.0f}%)", f"- Rs {pay['commission']}", False),
                             ("Worker receives directly", f"Rs {pay['net']}", True)]:
        size = 12 if bold else 11
        text(22 * mm, y, label, "Helvetica-Bold" if bold else "Helvetica", size)
        cv.setFillColorRGB(0, 0, 0)
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        cv.drawRightString(W - 22 * mm, y, val)
        y -= 8 * mm

    y += 2 * mm
    cv.line(18 * mm, y, W - 18 * mm, y)
    y -= 9 * mm
    text(18 * mm, y, f"For comparison: typical private apps keep 20-25% "
                    f"(worker would get ~Rs {int(pay['amount'] * 0.78)}).", "Helvetica-Oblique", 10)
    y -= 7 * mm
    text(18 * mm, y, "Payment reference: " + str(pay["gateway_ref"]) +
                    "  ·  Method: " + str(pay["method"]).upper(), size=9)
    y -= 8 * mm
    text(18 * mm, y, "DEMO MODE — no real money was transferred.", "Helvetica-Bold", 11, (0.55, 0.2, 0.1))
    text(18 * mm, 12 * mm, "SahkarSetu · Delhi Labour Cooperative Federation · Generated electronically",
         size=8.5, color=(0.35, 0.35, 0.35))
    cv.save()
    return buf.getvalue()

@app.get("/api/bookings/{bid}/invoice.pdf")
def invoice_pdf(bid: int, u=Depends(get_current_user_download)):
    b = q("""SELECT b.*, s.name_en service, s.unit, wu.name wname, c.name coop,
                    cu.name cust_name, cu.phone cust_phone
             FROM bookings b JOIN services s ON s.id=b.service_id
             LEFT JOIN workers w ON w.user_id=b.worker_id
             LEFT JOIN users wu ON wu.id=w.user_id
             LEFT JOIN cooperatives c ON c.id=w.coop_id
             JOIN users cu ON cu.id=b.customer_id WHERE b.id=?""", (bid,), one=True)
    if not b:
        raise HTTPException(404, "Not found")
    if u["id"] not in (b["customer_id"], b["worker_id"]) and u["role"] not in ("federation_admin", "super_admin"):
        raise HTTPException(403, "Not your invoice")
    pay = q("SELECT * FROM payments WHERE booking_id=?", (bid,), one=True)
    if not pay:
        raise HTTPException(400, "Payment pending — invoice after payment")
    pdf = make_invoice_pdf(dict(b), dict(pay))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=sahkarsetu-{b['code']}.pdf",
                             "Cache-Control": "no-store"})

# ---------------------------------------------------------------- worker APIs
@app.get("/api/w/home")
def worker_home(u=Depends(require_role("worker"))):
    w = q("""SELECT w.*, u.name, u.phone FROM workers w JOIN users u ON u.id=w.user_id
             WHERE w.user_id=?""", (u["id"],), one=True)
    if not w:
        raise HTTPException(404, "Worker profile missing")
    jobs = q("""SELECT b.id, b.code, b.scheduled_for, b.address, b.zone, b.status, b.price,
                       b.is_emergency, b.notes, s.name_en service, cu.name cust, cu.phone cust_phone
                FROM bookings b JOIN services s ON s.id=b.service_id
                JOIN users cu ON cu.id=b.customer_id
                WHERE b.worker_id=? AND b.status IN ('requested','accepted','enroute','in_progress')
                ORDER BY b.scheduled_for""", (u["id"],))
    hist = q("""SELECT b.id, b.code, b.status, b.price, b.completed_at, s.name_en service,
                       p.net my_net, p.commission
                FROM bookings b JOIN services s ON s.id=b.service_id
                LEFT JOIN payments p ON p.booking_id=b.id
                WHERE b.worker_id=? AND b.status IN ('completed','cancelled')
                ORDER BY b.id DESC LIMIT 25""", (u["id"],))
    wk_ago = (date.today() - timedelta(days=7)).isoformat()
    mo_start = date.today().replace(day=1).isoformat()
    earn_w = q("""SELECT COALESCE(SUM(p.net),0) n FROM payments p JOIN bookings b ON b.id=p.booking_id
                  WHERE b.worker_id=? AND date(b.scheduled_for)>=?""", (u["id"], wk_ago), one=True)["n"]
    earn_m = q("""SELECT COALESCE(SUM(p.net),0) n FROM payments p JOIN bookings b ON b.id=p.booking_id
                  WHERE b.worker_id=? AND date(b.scheduled_for)>=?""", (u["id"], mo_start), one=True)["n"]
    earn_all = q("SELECT COALESCE(SUM(p.net),0) n FROM payments p JOIN bookings b ON b.id=p.booking_id WHERE b.worker_id=?",
                 (u["id"],), one=True)["n"]
    welfare = [dict(r) for r in q("SELECT scheme, valid_till, status FROM welfare WHERE worker_id=?", (u["id"],))]
    coop = q("SELECT c.name, c.zone FROM cooperatives c WHERE c.id=?", (w["coop_id"],), one=True)
    certs = [dict(r) for r in q("""SELECT id, title, issuer, year, status FROM certifications
                                   WHERE worker_id=? ORDER BY id DESC""", (u["id"],))]
    claims = [dict(r) for r in q("""SELECT id, scheme, reason, amount, status, created_at
                                    FROM welfare_claims WHERE worker_id=? ORDER BY id DESC LIMIT 10""",
                                 (u["id"],))]
    ver_certs = sum(1 for c in certs if c["status"] == "verified")
    return {"worker": dict(w), "coop": dict(coop), "jobs": [dict(r) for r in jobs],
            "history": [dict(r) for r in hist],
            "earnings": {"week": earn_w, "month": earn_m, "lifetime": earn_all},
            "welfare": welfare, "certifications": certs, "claims": claims,
            "skill_level": _skill_of(w["exp_years"], ver_certs, w["rating_avg"], w["jobs_done"])}

@app.post("/api/w/certs")
def add_cert(b: CertIn, u=Depends(require_role("worker"))):
    """PS clause 'worker skill profiling and certification': a worker may add his own
    certificates. They show as PENDING until the cooperative society verifies them -
    only verified certificates feed the skill profile and the public badge."""
    n = q("SELECT COUNT(*) n FROM certifications WHERE worker_id=?", (u["id"],), one=True)["n"]
    if n >= 6:
        raise HTTPException(400, "6 se zyada certificate add nahi ho sakte")
    yr = min(int(b.year), date.today().year)
    with tx() as conn:
        cur = conn.execute("""INSERT INTO certifications(worker_id,title,issuer,year,verified_by_coop,status)
                              VALUES(?,?,?,?,0,'pending')""",
                           (u["id"], b.title.strip(), (b.issuer or "Self-declared").strip(), yr))
        cid = cur.lastrowid
    return {"ok": True, "id": cid, "status": "pending",
            "message": "Certificate jama. Samiti verification ke baad badge milega."}

@app.post("/api/w/welfare/apply")
def welfare_apply(a: WelfareApplyIn, u=Depends(require_role("worker"))):
    """Worker-initiated welfare enrolment (PS clause 'worker welfare and insurance
    integration'). The society/federation approves; only then does cover start."""
    if a.scheme not in ("PMSBY", "PMJJBY"):
        raise HTTPException(400, "Bad scheme")
    st = q("SELECT status FROM workers WHERE user_id=?", (u["id"],), one=True)
    if not st or st["status"] != "verified":
        raise HTTPException(403, "Samiti verification ke baad hi welfare milta hai")
    dup = q("""SELECT status FROM welfare WHERE worker_id=? AND scheme=? AND status IN ('active','pending')""",
            (u["id"], a.scheme), one=True)
    if dup:
        raise HTTPException(409, "Ye scheme pehle se " + ("active hai" if dup["status"] == "active" else "review mein hai"))
    ex("""INSERT INTO welfare(worker_id,scheme,status,requested_by,requested_on)
          VALUES(?,?,'pending','worker',datetime('now'))""", (u["id"], a.scheme))
    return {"ok": True, "status": "pending", "message": "Application bheji — samiti approve karegi."}

@app.post("/api/w/welfare/claim")
def welfare_claim(c: ClaimIn, u=Depends(require_role("worker"))):
    """Insurance claim request against an ACTIVE scheme; the society/federation decides."""
    if c.scheme not in ("PMSBY", "PMJJBY"):
        raise HTTPException(400, "Bad scheme")
    act = q("SELECT 1 FROM welfare WHERE worker_id=? AND scheme=? AND status='active'",
            (u["id"], c.scheme), one=True)
    if not act:
        raise HTTPException(409, "Pehle scheme active honi chahiye (PMSBY/PMJJBY)")
    ex("""INSERT INTO welfare_claims(worker_id,scheme,reason,amount,status)
          VALUES(?,?,?,?,'filed')""", (u["id"], c.scheme, c.reason.strip(), c.amount))
    return {"ok": True, "status": "filed", "message": "Claim darj — samiti review karegi."}

ALLOWED_NEXT = {"requested": ["accepted"], "accepted": ["enroute"], "enroute": ["in_progress"],
                "in_progress": ["completed"]}

@app.post("/api/w/jobs/{bid}/status")
def job_status(bid: int, si: StatusIn, u=Depends(require_role("worker"))):
    b = q("SELECT * FROM bookings WHERE id=? AND worker_id=?", (bid, u["id"]), one=True)
    if not b:
        raise HTTPException(404, "Job not found")
    if si.status not in ALLOWED_NEXT.get(b["status"], []):
        raise HTTPException(400, f"Cannot move {b['status']} -> {si.status}")
    # one active job per worker: must finish/decline before taking another.
    if si.status == "accepted" and q(
            """SELECT 1 FROM bookings WHERE worker_id=? AND id!=? AND status IN
               ('accepted','enroute','in_progress') LIMIT 1""",
            (u["id"], bid), one=True):
        raise HTTPException(409, "Pehle apna chalu kaam poora karein — ek time pe ek hi job.")
    with tx() as conn:
        conn.execute("UPDATE bookings SET status=?, completed_at=? WHERE id=?",
                     (si.status, datetime.now().isoformat() if si.status == "completed" else b["completed_at"], bid))
        if si.status == "completed":
            conn.execute("UPDATE workers SET jobs_done = jobs_done + 1 WHERE user_id=?", (u["id"],))
    ev(bid, si.status, actor=u["name"])
    return {"ok": True, "status": si.status}

@app.post("/api/w/jobs/{bid}/decline")
def decline_job(bid: int, u=Depends(require_role("worker"))):
    """Worker agency: a worker may decline an unaccepted offer. The booking is then
    re-routed to the next nearest free worker - never back to the decliner.
    If nobody free is left it is cancelled honestly instead of stalling forever."""
    b = q("SELECT * FROM bookings WHERE id=? AND worker_id=?", (bid, u["id"]), one=True)
    if not b:
        raise HTTPException(404, "Job not found")
    if b["status"] != "requested":
        raise HTTPException(400, "Sirf nayi request decline ho sakti hai")
    svc = q("SELECT * FROM services WHERE id=?", (b["service_id"],), one=True)
    ex("INSERT OR IGNORE INTO declines(booking_id,worker_id) VALUES(?,?)", (bid, u["id"]))
    ev(bid, "declined", f"{svc['name_en'] if svc else ''}".strip(), actor=u["name"])
    declined = [r["worker_id"] for r in q("SELECT worker_id FROM declines WHERE booking_id=?", (bid,))]
    nxt = find_matches(svc, b["zone"], limit=1, exclude_ids=declined) if svc else []
    if nxt:
        m = nxt[0]
        with tx() as conn:
            conn.execute("UPDATE bookings SET worker_id=? WHERE id=?", (m["id"], bid))
        ev(bid, "redispatched",
           f"{m['name']} — {m['distance_km']} km" if m.get("distance_km") is not None else m["name"],
           actor="system")
        return {"ok": True, "reassigned": {"id": m["id"], "name": m["name"], "distance_km": m["distance_km"]}}
    with tx() as conn:
        conn.execute("""UPDATE bookings SET status='cancelled',
                        notes = COALESCE(notes,'') || ' [auto-cancelled: no free worker]' WHERE id=?""", (bid,))
    return {"ok": True, "reassigned": None, "cancelled": True,
            "note": "Aapne mana kiya aur koi doosra free worker nahi mila — booking cancel kar di gayi."}

# ---------------------------------------------------------------- admin APIs
ADMIN_READ = ("federation_admin", "super_admin")
ADMIN_WRITE = ("federation_admin",)

@app.get("/api/a/overview")
def admin_overview(u=Depends(require_role(*ADMIN_READ))):
    t = date.today().isoformat()
    wk_ago = (date.today() - timedelta(days=7)).isoformat()
    mo_start = date.today().replace(day=1).isoformat()
    # one round-trip instead of the old per-stat double query (16 queries -> 1)
    row = q("""SELECT
        (SELECT COUNT(*) FROM workers) workers_total,
        (SELECT COUNT(*) FROM workers WHERE status='verified') workers_verified,
        (SELECT COUNT(*) FROM workers WHERE status='pending') pending_verify,
        (SELECT COUNT(*) FROM users WHERE role='customer') customers,
        (SELECT COUNT(*) FROM bookings WHERE date(created_at)=?) bookings_today,
        (SELECT COALESCE(SUM(amount),0) FROM payments p JOIN bookings b ON b.id=p.booking_id
          WHERE date(b.scheduled_for)>=?) week_gmv,
        (SELECT COALESCE(SUM(commission),0) FROM payments p JOIN bookings b ON b.id=p.booking_id
          WHERE date(b.scheduled_for)>=?) month_commission,
        (SELECT COUNT(DISTINCT worker_id) FROM welfare WHERE status='active') welfare_enrolled,
        (SELECT COALESCE(SUM(net)*100.0/NULLIF(SUM(amount),0),90) FROM payments) worker_share""",
        (t, wk_ago, mo_start), one=True)
    stats = {k: row[k] for k in ("workers_total", "workers_verified", "pending_verify", "customers",
                                 "bookings_today", "week_gmv", "month_commission", "welfare_enrolled")}
    stats["worker_share_pct"] = round(row["worker_share"], 1)
    active = q("""SELECT b.id, b.code, b.status, b.is_emergency, b.zone, b.address,
                         w.lat, w.lng, wu.name wname, s.name_en service, cu.name cust
                  FROM bookings b
                  LEFT JOIN workers w ON w.user_id=b.worker_id
                  LEFT JOIN users wu ON wu.id=w.user_id
                  JOIN services s ON s.id=b.service_id
                  JOIN users cu ON cu.id=b.customer_id
                  WHERE b.status IN ('requested','accepted','enroute','in_progress')
                  ORDER BY b.id DESC LIMIT 40""")
    recent = q("""SELECT b.id, b.code, b.status, b.price, b.created_at, s.name_en service,
                         wu.name wname, cu.name cust, b.is_emergency
                  FROM bookings b JOIN services s ON s.id=b.service_id
                  LEFT JOIN workers w ON w.user_id=b.worker_id
                  LEFT JOIN users wu ON wu.id=w.user_id
                  JOIN users cu ON cu.id=b.customer_id
                  ORDER BY b.id DESC LIMIT 12""")
    trades = q("""SELECT s.trade, COUNT(*) n FROM bookings b JOIN services s ON s.id=b.service_id
                  WHERE date(b.scheduled_for)>=? GROUP BY s.trade ORDER BY n DESC""", (wk_ago,))
    return {"stats": stats, "active_jobs": [dict(r) for r in active],
            "recent_bookings": [dict(r) for r in recent],
            "week_by_trade": [dict(r) for r in trades]}

@app.get("/api/a/pending-workers")
def pending_workers(u=Depends(require_role(*ADMIN_READ))):
    rows = q("""SELECT w.user_id id, u.name, u.phone, w.trade, w.exp_years, c.name coop,
                       w.e_shram_uan, u.created_at
                FROM workers w JOIN users u ON u.id=w.user_id JOIN cooperatives c ON c.id=w.coop_id
                WHERE w.status='pending' ORDER BY u.created_at""")
    out = []
    for r in rows:
        certs = [dict(x) for x in q("SELECT title, issuer, year, verified_by_coop FROM certifications WHERE worker_id=?", (r["id"],))]
        out.append({**dict(r), "certifications": certs})
    return {"pending": out}

@app.post("/api/a/verify/{wid}")
def verify_worker(wid: int, v: VerifyIn, u=Depends(require_role(*ADMIN_WRITE))):
    w = q("SELECT * FROM workers WHERE user_id=?", (wid,), one=True)
    if not w:
        raise HTTPException(404, "Not found")
    if w["status"] != "pending":
        raise HTTPException(409, "Already processed")
    new_status = "verified" if v.approve else "suspended"
    with tx() as conn:
        conn.execute("UPDATE workers SET status=? WHERE user_id=?", (new_status, wid))
        if v.approve:
            # certificates are only blessed when the worker is actually approved
            conn.execute("UPDATE certifications SET verified_by_coop=1 WHERE worker_id=?", (wid,))
    return {"ok": True, "new_status": new_status}

@app.post("/api/a/payouts/run")
def payout_run(p: PayoutRunIn, u=Depends(require_role(*ADMIN_WRITE))):
    try:
        start, end = date.fromisoformat(p.period_start), date.fromisoformat(p.period_end)
    except ValueError:
        raise HTTPException(400, "Dates YYYY-MM-DD format mein chahiye")
    if start > end:
        raise HTTPException(400, "Period ka start, end se pehle hona chahiye")
    dup = q("SELECT id FROM payout_runs WHERE period_start=? AND period_end=?",
            (start.isoformat(), end.isoformat()), one=True)
    if dup and not p.confirm_duplicate:
        raise HTTPException(409, f"Is period ka payout run #{dup['id']} already ho chuka hai. "
                                 f"Dobara chalane par bank CSV duplicate banega — confirm karein.")
    # Only jobs that have NEVER been in a payout run. Without this, a second run whose
    # period overlapped the first paid the same job again (nothing marked a job settled).
    items = q("""SELECT pay.booking_id, w.user_id wid, pay.amount gross, pay.commission comm, pay.net net
                 FROM bookings b
                 JOIN payments pay ON pay.booking_id=b.id
                 JOIN workers w ON w.user_id=b.worker_id
                 WHERE date(b.scheduled_for)>=? AND date(b.scheduled_for)<=?
                   AND pay.booking_id NOT IN (SELECT booking_id FROM payout_items)""",
              (start.isoformat(), end.isoformat()))
    settled = q("""SELECT COUNT(*) n FROM bookings b JOIN payments pay ON pay.booking_id=b.id
                   WHERE date(b.scheduled_for)>=? AND date(b.scheduled_for)<=?
                     AND pay.booking_id IN (SELECT booking_id FROM payout_items)""",
                (start.isoformat(), end.isoformat()), one=True)["n"]
    per = {}
    for it in items:
        a = per.setdefault(it["wid"], {"jobs": 0, "gross": 0, "comm": 0, "net": 0})
        a["jobs"] += 1
        a["gross"] += it["gross"] or 0
        a["comm"] += it["comm"] or 0
        a["net"] += it["net"] or 0
    tot_comm = sum(a["comm"] for a in per.values())
    tot_net = sum(a["net"] for a in per.values())
    tot_jobs = sum(a["jobs"] for a in per.values())
    with tx() as conn:
        cur = conn.execute("""INSERT INTO payout_runs(period_start,period_end,total_net,total_commission,
                   worker_count,job_count,status,created_by) VALUES(?,?,?,?,?,?, 'executed', ?)""",
                           (start.isoformat(), end.isoformat(), tot_net, tot_comm, len(per), tot_jobs, u["name"]))
        rid = cur.lastrowid
        conn.executemany("INSERT INTO payout_items(run_id,booking_id,worker_id,net) VALUES(?,?,?,?)",
                         [(rid, it["booking_id"], it["wid"], it["net"]) for it in items])
    meta = {r["user_id"]: dict(r) for r in (
        q("""SELECT w.user_id, u.name, u.phone, c.name coop, w.trade
             FROM workers w JOIN users u ON u.id=w.user_id
             LEFT JOIN cooperatives c ON c.id=w.coop_id
             WHERE w.user_id IN (%s)""" % ",".join("?" * len(per)), tuple(per)) if per else [])}
    fn = f"data/payout_{rid}.csv"
    with open(os.path.join(BASE, fn), "w", newline="") as fh:
        wtr = _csv.writer(fh)
        wtr.writerow(["worker_id", "name", "phone", "cooperative", "trade", "jobs", "gross", "commission", "net_to_worker"])
        for wid, a in sorted(per.items(), key=lambda kv: -kv[1]["net"]):
            m = meta.get(wid, {})
            wtr.writerow([wid, m.get("name", ""), m.get("phone", ""), m.get("coop", ""), m.get("trade", ""),
                          a["jobs"], a["gross"], a["comm"], a["net"]])
        wtr.writerow([])
        wtr.writerow(["TOTAL", "", "", "", "", tot_jobs, "", tot_comm, tot_net])
    return {"run_id": rid, "workers": len(per), "jobs": tot_jobs, "total_net": tot_net,
            "total_commission": tot_comm, "already_settled_skipped": settled,
            "csv": f"/api/a/payouts/csv/{rid}"}

@app.get("/api/a/payouts/csv/{rid}")
def payout_csv(rid: int, u=Depends(get_current_user_download)):
    path = os.path.join(BASE, "data", f"payout_{rid}.csv")
    if not os.path.exists(path):
        raise HTTPException(404, "CSV not found")
    return FileResponse(path, media_type="text/csv",
                        headers={"Cache-Control": "no-store"},
                        filename=f"sahkarsetu_payout_{rid}.csv")

@app.get("/api/a/payouts")
def payout_history(u=Depends(require_role(*ADMIN_READ))):
    rows = [dict(r) for r in q("SELECT * FROM payout_runs ORDER BY id DESC LIMIT 20")]
    return {"runs": rows}

@app.get("/api/a/welfare")
def welfare_overview(u=Depends(require_role(*ADMIN_READ))):
    total = q("SELECT COUNT(*) n FROM workers WHERE status='verified'", one=True)["n"]
    pmsby = q("SELECT COUNT(*) n FROM welfare WHERE scheme='PMSBY' AND status='active'", one=True)["n"]
    pmjjby = q("SELECT COUNT(*) n FROM welfare WHERE scheme='PMJJBY' AND status='active'", one=True)["n"]
    rows = q("""SELECT w.user_id id, u.name, c.name coop, w.trade,
                       GROUP_CONCAT(wf.scheme) schemes
                FROM workers w JOIN users u ON u.id=w.user_id
                JOIN cooperatives c ON c.id=w.coop_id
                LEFT JOIN welfare wf ON wf.worker_id=w.user_id AND wf.status='active'
                WHERE w.status='verified'
                GROUP BY w.user_id ORDER BY u.name""")
    return {"totals": {"verified": total, "pmsby": pmsby, "pmjjby": pmjjby,
                       "pmsby_cost_note": "PMSBY: Rs 20/year per worker -> Rs 2 lakh accident cover",
                       "pmjjby_cost_note": "PMJJBY: Rs 436/year -> Rs 2 lakh life cover"},
            "workers": [dict(r) for r in rows]}

@app.post("/api/a/welfare/enroll")
def welfare_enroll(wi: WelfareIn, u=Depends(require_role(*ADMIN_WRITE))):
    if wi.scheme not in ("PMSBY", "PMJJBY"):
        raise HTTPException(400, "Bad scheme")
    w = q("SELECT status FROM workers WHERE user_id=?", (wi.worker_id,), one=True)
    if not w or w["status"] != "verified":
        raise HTTPException(404, "Verified worker not found")
    dup = q("SELECT 1 FROM welfare WHERE worker_id=? AND scheme=? AND status='active'",
            (wi.worker_id, wi.scheme), one=True)
    if dup:
        raise HTTPException(409, "Already enrolled")
    yr = date.today().year
    ex("INSERT INTO welfare(worker_id,scheme,enrolled_on,valid_till,status) VALUES(?,?,?,?,'active')",
       (wi.worker_id, wi.scheme, f"{yr}-04-01", f"{yr+1}-03-31"))
    return {"ok": True}

# ---- welfare workflow + certification verification (shared by federation and society) ----
def _decide_enrolment(worker_id, scheme, approve, actor, coop_id=None):
    """Approve a worker's pending welfare application (or reject it). Scoped to one
    cooperative when a society admin is acting, unrestricted for the federation."""
    extra, args = "", [worker_id, scheme]
    if coop_id is not None:
        extra, args = " AND wk.coop_id=?", [worker_id, scheme, coop_id]
    row = q(f"""SELECT wf.id FROM welfare wf JOIN workers wk ON wk.user_id=wf.worker_id
                WHERE wf.worker_id=? AND wf.scheme=? AND wf.status='pending'{extra}""", args, one=True)
    if not row:
        raise HTTPException(404, "Pending welfare application nahi mili")
    yr = date.today().year
    if approve:
        ex("""UPDATE welfare SET status='active', enrolled_on=?, valid_till=?, decided_by=?
              WHERE id=?""", (f"{yr}-04-01", f"{yr + 1}-03-31", actor, row["id"]))
    else:
        ex("UPDATE welfare SET status='rejected', decided_by=? WHERE id=?", (actor, row["id"]))
    return {"ok": True, "status": "active" if approve else "rejected"}

def _decide_claim(cid, approve, actor, coop_id=None):
    """Approve/reject a filed insurance claim, optionally scoped to one cooperative."""
    extra, args = "", [cid]
    if coop_id is not None:
        extra, args = " AND wk.coop_id=?", [cid, coop_id]
    row = q(f"""SELECT cl.id FROM welfare_claims cl JOIN workers wk ON wk.user_id=cl.worker_id
                WHERE cl.id=? AND cl.status='filed'{extra}""", args, one=True)
    if not row:
        raise HTTPException(404, "Filed claim nahi mila")
    ex("""UPDATE welfare_claims SET status=?, decided_at=datetime('now'), decided_by=? WHERE id=?""",
       ("approved" if approve else "rejected", actor, cid))
    return {"ok": True, "status": "approved" if approve else "rejected"}

def _cert_decide(cid, approve, coop_id=None):
    """A certificate only counts once a cooperative verifies it (PS: certification)."""
    extra, args = "", [cid]
    if coop_id is not None:
        extra, args = " AND w.coop_id=?", [cid, coop_id]
    c = q(f"""SELECT c.id FROM certifications c JOIN workers w ON w.user_id=c.worker_id
              WHERE c.id=?{extra}""", args, one=True)
    if not c:
        raise HTTPException(404, "Certificate nahi mila")
    st = "verified" if approve else "rejected"
    ex("UPDATE certifications SET status=?, verified_by_coop=? WHERE id=?",
       (st, 1 if approve else 0, cid))
    return {"ok": True, "status": st}

@app.get("/api/a/certs/pending")
def certs_pending(coop: int = None, u=Depends(require_role(*ADMIN_READ))):
    cwhere, args = "", []
    if coop:
        cwhere, args = " AND w.coop_id=?", [coop]
    rows = q(f"""SELECT c.id, c.worker_id, c.title, c.issuer, c.year, u.name, co.name coop
                 FROM certifications c JOIN users u ON u.id=c.worker_id
                 JOIN workers w ON w.user_id=c.worker_id
                 JOIN cooperatives co ON co.id=w.coop_id
                 WHERE c.status='pending'{cwhere} ORDER BY c.id""", args)
    return {"pending": [dict(r) for r in rows]}

@app.post("/api/a/certs/{cid}")
def cert_decide(cid: int, d: DecideIn, u=Depends(require_role(*ADMIN_WRITE))):
    return _cert_decide(cid, d.approve)

@app.get("/api/a/welfare/requests")
def welfare_requests(coop: int = None, u=Depends(require_role(*ADMIN_READ))):
    """Pending welfare applications + filed claims awaiting a decision."""
    cwhere, args = "", []
    if coop:
        cwhere, args = " AND wk.coop_id=?", [coop]
    pens = q(f"""SELECT wf.id, wf.worker_id, wf.scheme, wf.requested_by, wf.requested_on,
                        u.name, co.name coop, co.id coop_id
                 FROM welfare wf JOIN users u ON u.id=wf.worker_id
                 JOIN workers wk ON wk.user_id=wf.worker_id
                 JOIN cooperatives co ON co.id=wk.coop_id
                 WHERE wf.status='pending'{cwhere} ORDER BY wf.id""", args)
    claims = q(f"""SELECT cl.id, cl.worker_id, cl.scheme, cl.reason, cl.amount, cl.created_at,
                          u.name, co.name coop, co.id coop_id
                   FROM welfare_claims cl JOIN users u ON u.id=cl.worker_id
                   JOIN workers wk ON wk.user_id=cl.worker_id
                   JOIN cooperatives co ON co.id=wk.coop_id
                   WHERE cl.status='filed'{cwhere} ORDER BY cl.id""", args)
    return {"enrolments": [dict(r) for r in pens], "claims": [dict(r) for r in claims]}

@app.post("/api/a/welfare/decide")
def welfare_request_decide(d: WelfareDecideIn, u=Depends(require_role(*ADMIN_WRITE))):
    return _decide_enrolment(d.worker_id, d.scheme, d.approve, u["name"])

@app.post("/api/a/welfare/claim/{cid}")
def welfare_claim_decide(cid: int, d: DecideIn, u=Depends(require_role(*ADMIN_WRITE))):
    return _decide_claim(cid, d.approve, u["name"])

@app.get("/api/a/allocation")
def allocation_board(u=Depends(require_role(*ADMIN_READ))):
    """PS clause 'AI-based demand forecasting and workforce allocation': forecast demand
    (next 7 days from the explainable model) against VERIFIED supply per zone+trade,
    with a plain-language action the federation can take today."""
    demand = {}
    for r in compute_forecast()["rows"]:
        k = (r["zone"], r["trade"])
        demand[k] = demand.get(k, 0.0) + (r.get("predicted") or 0)
    supply = {(r["zone"], r["trade"]): dict(r) for r in q("""
        SELECT w.zone, w.trade,
               SUM(CASE WHEN w.status='verified' THEN 1 ELSE 0 END) verified,
               SUM(CASE WHEN w.status='pending' THEN 1 ELSE 0 END) pending,
               SUM(CASE WHEN EXISTS (SELECT 1 FROM bookings b WHERE b.worker_id=w.user_id
                        AND b.status IN ('accepted','enroute','in_progress')) THEN 1 ELSE 0 END) busy
        FROM workers w GROUP BY w.zone, w.trade""")}
    recent = {(r["zone"], r["trade"]): r["n"] for r in q("""
        SELECT b.zone, s.trade, COUNT(*) n FROM bookings b JOIN services s ON s.id=b.service_id
        WHERE b.status='completed'
          AND date(COALESCE(b.completed_at, b.scheduled_for)) >= date('now','-7 days')
        GROUP BY b.zone, s.trade""")}
    rows = []
    for k in sorted(set(demand) | set(supply)):
        zone, trade = k
        fc7 = round(demand.get(k, 0.0), 1)
        s = supply.get(k, {})
        ver, pend, busy = s.get("verified") or 0, s.get("pending") or 0, s.get("busy") or 0
        free = max(ver - busy, 0)
        jobs7 = recent.get(k, 0)
        per = round(fc7 / ver, 2) if ver else None
        if ver == 0 and fc7 > 0:
            sev, action = "critical", f"{zone}: no verified {trade} — recruit now, {fc7} jobs expected"
        elif per is not None and per >= 3:
            need = max(0, -(-int(fc7) // 3) - ver)
            sev = "deficit"
            action = (f"{zone}: {fc7} jobs expected vs {ver} {trade} — "
                      f"{'add/shift ~' + str(need) + ' worker(s)' if need else 'watch closely'}"
                      + (f", {pend} in verification queue" if pend else ""))
        elif ver and fc7 == 0:
            sev, action = "surplus", f"{zone}: {ver} {trade}, no forecast demand — offer cross-zone jobs"
        else:
            sev, action = "ok", f"{zone}: {fc7} jobs vs {free} free now — balanced"
        rows.append({"zone": zone, "trade": trade, "forecast_7d": fc7, "verified": ver,
                     "pending": pend, "busy": busy, "free_now": free, "jobs_7d": jobs7,
                     "jobs_per_worker": per, "severity": sev, "action": action})
    order = {"critical": 0, "deficit": 1, "surplus": 2, "ok": 3}
    rows.sort(key=lambda r: (order[r["severity"]], -r["forecast_7d"]))
    return {"rows": rows, "note": "Allocation made visible: forecast (next 7 days) vs verified "
                                  "workers — the federation decides, nothing is auto-forced."}

@app.get("/api/a/forecast")
def admin_forecast(zone: str = None, trade: str = None,
                   u=Depends(require_role(*ADMIN_READ))):
    fc = compute_forecast(zone, trade)
    return fc

@app.get("/api/a/forecast/summary")
def admin_forecast_summary(u=Depends(require_role(*ADMIN_READ))):
    return forecast_summary()

# ---------------------------------------------------------------- static
# Cache policy: hashed/immutable-ish assets cache hard; HTML + sw.js stay revalidating
# (sw.js must always be fresh or browsers pin a stale service worker for 24h).
class CachedStatic(StaticFiles):
    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        # starlette signature: file_response(full_path, stat_result, scope, status_code=200)
        # (the old build read args[1] - a stat_result - so the sw.js branch never fired)
        full_path = str(args[0]) if args else ""
        if "text/html" in resp.headers.get("content-type", "") or full_path.endswith("sw.js"):
            resp.headers["Cache-Control"] = "no-cache"
        else:
            resp.headers["Cache-Control"] = "public, max-age=604800"
        return resp

# ---------------------------------------------------------------- cooperative society
# The PS names BOTH federations and labour cooperative societies. A society admin gets
# a dashboard hard-scoped to his own samiti (workers, verification, welfare, earnings);
# the federation can inspect any society with ?coop=<id>.
COOP_READ = ("coop_admin", "federation_admin", "super_admin")
COOP_WRITE = ("coop_admin", "federation_admin")

def _coop_scope(u, coop: int = None):
    if u["role"] == "coop_admin":
        try:
            cid = dict(u).get("coop_id")
        except (TypeError, ValueError):
            cid = None
        if not cid:
            raise HTTPException(403, "Aapki samiti mapping missing hai — federation se sampark karein")
        return cid
    if not coop:
        raise HTTPException(400, "Federation ke liye ?coop=<id> chahiye")
    return coop

@app.get("/api/c/home")
def society_home(coop: int = None, u=Depends(require_role(*COOP_READ))):
    cid = _coop_scope(u, coop)
    c = q("""SELECT c.id, c.name, c.zone, c.district, f.name fed FROM cooperatives c
             LEFT JOIN federations f ON f.id=c.federation_id WHERE c.id=?""", (cid,), one=True)
    if not c:
        raise HTTPException(404, "Samiti nahi mili")
    wk = [dict(r) for r in q("""
        SELECT w.user_id id, u.name, u.phone, w.trade, w.status, w.rating_avg, w.rating_count,
               w.jobs_done, w.exp_years, w.e_shram_uan,
               (SELECT COUNT(*) FROM certifications c WHERE c.worker_id=w.user_id AND c.status='verified') certs_verified,
               (SELECT COUNT(*) FROM certifications c WHERE c.worker_id=w.user_id AND c.status='pending') certs_pending,
               (SELECT GROUP_CONCAT(wf.scheme) FROM welfare wf WHERE wf.worker_id=w.user_id AND wf.status='active') welfare,
               (SELECT COUNT(*) FROM bookings b WHERE b.worker_id=w.user_id
                 AND b.status IN ('accepted','enroute','in_progress')) active_jobs,
               (SELECT COALESCE(SUM(p.net),0) FROM payments p JOIN bookings b ON b.id=p.booking_id
                 WHERE b.worker_id=w.user_id) net_paid
        FROM workers w JOIN users u ON u.id=w.user_id WHERE w.coop_id=? ORDER BY u.name""", (cid,))]
    for r in wk:
        r["busy"] = (r["active_jobs"] or 0) > 0
        r["skill_level"] = _skill_of(r["exp_years"], r["certs_verified"], r["rating_avg"], r["jobs_done"])
        r["insured"] = bool((r["welfare"] or "").strip())
        r["phone"] = _mask_phone(r["phone"])
    live = [dict(r) for r in q("""
        SELECT b.id, b.code, b.status, b.scheduled_for, b.price, b.zone, s.name_en service,
               cu.name cust, wu.name worker, b.is_emergency
        FROM bookings b JOIN services s ON s.id=b.service_id
        JOIN users cu ON cu.id=b.customer_id
        JOIN workers w ON w.user_id=b.worker_id JOIN users wu ON wu.id=b.worker_id
        WHERE w.coop_id=? AND b.status IN ('requested','accepted','enroute','in_progress')
        ORDER BY b.scheduled_for LIMIT 25""", (cid,))]
    events = [dict(r) for r in q("""
        SELECT e.kind, e.detail, e.actor, e.created_at, e.booking_id, b.code
        FROM booking_events e JOIN bookings b ON b.id=e.booking_id
        JOIN workers w ON w.user_id=b.worker_id
        WHERE w.coop_id=? ORDER BY e.id DESC LIMIT 15""", (cid,))]
    money = q("""SELECT COALESCE(SUM(p.amount),0) gross, COALESCE(SUM(p.commission),0) commission,
                        COALESCE(SUM(p.net),0) worker_net, COUNT(*) jobs
                 FROM payments p JOIN bookings b ON b.id=p.booking_id
                 JOIN workers w ON w.user_id=b.worker_id WHERE w.coop_id=?""", (cid,), one=True)
    today = q("""SELECT COUNT(*) n FROM bookings b JOIN workers w ON w.user_id=b.worker_id
                 WHERE w.coop_id=? AND date(b.created_at)=date('now')""", (cid,), one=True)["n"]
    welfare_reqs = q("""SELECT wf.id, wf.worker_id, wf.scheme, wf.requested_by, wf.requested_on, u.name
                        FROM welfare wf JOIN users u ON u.id=wf.worker_id
                        JOIN workers wk ON wk.user_id=wf.worker_id
                        WHERE wk.coop_id=? AND wf.status='pending' ORDER BY wf.id""", (cid,))
    claims = q("""SELECT cl.id, cl.worker_id, cl.scheme, cl.reason, cl.amount, cl.created_at, u.name
                  FROM welfare_claims cl JOIN users u ON u.id=cl.worker_id
                  JOIN workers wk ON wk.user_id=cl.worker_id
                  WHERE wk.coop_id=? AND cl.status='filed' ORDER BY cl.id""", (cid,))
    cert_q = q("""SELECT c.id, c.worker_id, c.title, c.issuer, c.year, u.name
                  FROM certifications c JOIN users u ON u.id=c.worker_id
                  JOIN workers w ON w.user_id=c.worker_id
                  WHERE w.coop_id=? AND c.status='pending' ORDER BY c.id""", (cid,))
    ver = sum(1 for r in wk if r["status"] == "verified")
    pend = sum(1 for r in wk if r["status"] == "pending")
    ins = sum(1 for r in wk if r["insured"])
    # demand for THIS society's zone: same explainable model the federation sees
    fcz = {}
    for r in compute_forecast(zone=c["zone"])["rows"]:
        fcz[r["trade"]] = fcz.get(r["trade"], 0.0) + (r.get("predicted") or 0)
    return {"coop": dict(c), "zone_demand_7d": {k: round(v, 1) for k, v in fcz.items()},
            "stats": {"workers": len(wk), "verified": ver, "pending": pend, "insured": ins,
                      "live_jobs": len(live), "jobs_today": today,
                      "gross": money["gross"], "commission": money["commission"],
                      "worker_net": money["worker_net"], "jobs_paid": money["jobs"],
                      "certs_pending": len(cert_q), "welfare_pending": len(welfare_reqs),
                      "claims_filed": len(claims)},
            "workers": wk, "live": live, "events": events,
            "pending_certs": [dict(r) for r in cert_q],
            "welfare_requests": [dict(r) for r in welfare_reqs],
            "claims": [dict(r) for r in claims]}

@app.get("/api/c/pending-workers")
def society_pending(coop: int = None, u=Depends(require_role(*COOP_READ))):
    cid = _coop_scope(u, coop)
    rows = q("""SELECT w.user_id id, u.name, u.phone, w.trade, w.exp_years, w.e_shram_uan, u.created_at,
                       (SELECT COUNT(*) FROM certifications c
                         WHERE c.worker_id=w.user_id AND c.status='pending') certs_pending
                FROM workers w JOIN users u ON u.id=w.user_id
                WHERE w.coop_id=? AND w.status='pending' ORDER BY u.created_at""", (cid,))
    return {"pending": [dict(r) for r in rows]}

@app.post("/api/c/verify/{wid}")
def society_verify(wid: int, v: VerifyIn, u=Depends(require_role(*COOP_WRITE))):
    """A society verifies its OWN workers (the federation can still do it too)."""
    cid = _coop_scope(u)
    w = q("SELECT * FROM workers WHERE user_id=? AND coop_id=?", (wid, cid), one=True)
    if not w:
        raise HTTPException(404, "Ye worker is samiti ka nahi hai")
    if w["status"] != "pending":
        raise HTTPException(409, "Already processed")
    new_status = "verified" if v.approve else "suspended"
    with tx() as conn:
        conn.execute("UPDATE workers SET status=? WHERE user_id=?", (new_status, wid))
        if v.approve:
            conn.execute("""UPDATE certifications SET status='verified', verified_by_coop=1
                            WHERE worker_id=?""", (wid,))
    return {"ok": True, "new_status": new_status}

@app.post("/api/c/certs/{cid}")
def society_cert_decide(cid: int, d: DecideIn, u=Depends(require_role(*COOP_WRITE))):
    return _cert_decide(cid, d.approve, coop_id=_coop_scope(u))

@app.post("/api/c/welfare/decide")
def society_welfare_decide(d: WelfareDecideIn, u=Depends(require_role(*COOP_WRITE))):
    return _decide_enrolment(d.worker_id, d.scheme, d.approve, u["name"], coop_id=_coop_scope(u))

@app.post("/api/c/welfare/claim/{cid}")
def society_claim_decide(cid: int, d: DecideIn, u=Depends(require_role(*COOP_WRITE))):
    return _decide_claim(cid, d.approve, u["name"], coop_id=_coop_scope(u))

# service worker must always revalidate (browsers pin a stale SW for up to 24h otherwise)
# NOTE: registered BEFORE the /static mount, or the mount matches first and this never fires.
@app.get("/static/sw.js", include_in_schema=False)
@app.head("/static/sw.js", include_in_schema=False)
def sw_nocache():
    return FileResponse(os.path.join(BASE, "static", "sw.js"),
                        media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})

app.mount("/static", CachedStatic(directory=os.path.join(BASE, "static")), name="static")

@app.get("/")
@app.head("/")
def index():
    return FileResponse(os.path.join(BASE, "static", "index.html"),
                        headers={"Cache-Control": "no-cache"})

@app.get("/api/health")
def health():
    """Cheap liveness + DB check (uptime monitors used to get 405 on HEAD /)."""
    try:
        n = q("SELECT COUNT(*) n FROM users", one=True)["n"]
        return {"ok": True, "db": "up", "users": n, "version": "sih26089-1.1"}
    except Exception as e:
        return JSONResponse({"ok": False, "db": "down", "error": str(e)[:120]}, status_code=503)

if __name__ == "__main__":
    print("[sahkarsetu] boot:", "db ready")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
