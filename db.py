"""SahkarSetu - Cooperative Gig Services Platform.
Database schema + seed data (SIH26089 build).
Demo project: all data is synthetic but patterned realistically.
"""
import os, sqlite3, json, hashlib, hmac, secrets, random, threading
from datetime import datetime, timedelta, date

BASE = os.path.dirname(os.path.abspath(__file__))
# Config is env-overridable so tests/QA runs can use an isolated copy of the DB
# (SAHKARSETU_DB) without touching the live one.
DATA_DIR = os.environ.get("SAHKARSETU_DATA_DIR") or os.path.join(BASE, "data")
DB_PATH = os.environ.get("SAHKARSETU_DB") or os.path.join(DATA_DIR, "sahkarsetu.db")

def _jwt_secret() -> str:
    """Env override -> persisted random key -> generated once at first boot.
    Never a hardcoded constant in source (that was the old demo posture)."""
    env = os.environ.get("SAHKARSETU_JWT_SECRET")
    if env:
        return env
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        key_path = os.path.join(DATA_DIR, "jwt_secret.key")
        if os.path.exists(key_path):
            with open(key_path) as fh:
                val = fh.read().strip()
            if val:
                return val
        val = secrets.token_urlsafe(48)
        with open(key_path, "w") as fh:
            fh.write(val)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return val
    except OSError:
        # read-only data dir (container, CI): ephemeral secret, sessions end at restart
        return secrets.token_urlsafe(48)

JWT_SECRET = _jwt_secret()

_conn = None
_db_lock = threading.RLock()

COMMISSION_PCT = 10.0  # flat, printed on every invoice

TRADES = [
    ("electrician", "बिजली मिस्त्री", "Electrician"),
    ("plumber", "प्लंबर", "Plumber"),
    ("carpenter", "बढ़ई", "Carpenter"),
    ("painter", "पेंटर", "Painter"),
    ("cleaning", "सफाईकर्मी", "Cleaning"),
    ("appliance", "AC व उपकरण मिस्त्री", "AC & Appliance Repair"),
    ("driver", "ड्राइवर", "Driver"),
    ("gardener", "माली", "Gardener"),
    ("cook", "रसोइया", "Cook"),
    ("caregiver", "देखभाल कर्मी", "Caregiver"),
    ("pest", "कीट नियंत्रण", "Pest Control"),
]

# real-ish Delhi localities: (zone_key, name_en, name_hi, lat, lng)
ZONES = [
    ("east",   "Seelampur",     "सीलमपुर",      28.6702, 77.2674),
    ("east",   "Mayur Vihar",   "मयूर विहार",    28.6057, 77.2900),
    ("south",  "Lajpat Nagar",  "लाजपत नगर",    28.5677, 77.2432),
    ("south",  "Saket",         "साकेत",         28.5245, 77.2066),
    ("central","Karol Bagh",    "करोल बाग",      28.6519, 77.1909),
    ("northw", "Rohini",        "रोहिणी",        28.7495, 77.0565),
    ("northw", "Pitampura",     "पीतमपुरा",      28.7031, 77.1320),
    ("southw", "Dwarka",        "द्वारका",       28.5921, 77.0460),
    ("south",  "Vasant Kunj",   "वसंत कुंज",     28.5210, 77.1585),
    ("east",   "Shahdara",      "शाहदरा",        28.6730, 77.2880),
]

SERVICES = [
    # slug, trade, en, hi, min, max, unit
    ("fan-motor-repair","electrician","Fan / Motor Repair","पंखा / मोटर मरम्मत",200,500,"visit"),
    ("full-house-wiring","electrician","Full House Wiring Check","पूरे घर की वायरिंग जाँच",1500,4000,"job"),
    ("mcb-switchboard","electrician","MCB / Switchboard Fix","एमसीबी / स्विचबोर्ड सुधार",300,800,"visit"),
    ("tap-leak-fix","plumber","Tap Leak Fix","नल रिसाव सुधार",150,400,"visit"),
    ("geyser-install","plumber","Geyser Installation","गीजर लगाना",800,1500,"unit"),
    ("blockage-clear","plumber","Drain Blockage Clearing","नाली की रुकावट साफ़",500,1200,"job"),
    ("furniture-repair","carpenter","Furniture Repair","फर्नीचर मरम्मत",400,1500,"job"),
    ("door-hinge-lock","carpenter","Door Hinge / Lock Fix","दरवाज़ा हिंज / ताला",250,700,"visit"),
    ("wardrobe-modular","carpenter","Wardrobe / Modular Work","अलमारी / मॉड्यूलर काम",3000,15000,"job"),
    ("room-paint","painter","Single Room Painting","कमरा पेंटिंग",1800,4500,"room"),
    ("wall-putty-exterior","painter","Wall Putty + Exterior Coat","पुट्टी + बाहरी कोट",8,15,"sqft"),
    ("deep-home-clean","cleaning","Deep Home Cleaning","गहरी घर की सफाई",1500,3500,"home"),
    ("bath-kitchen-clean","cleaning","Bathroom + Kitchen Clean","बाथरूम + किचन सफाई",500,1200,"visit"),
    ("ac-service","appliance","AC Service & Gas Top-up","एसी सर्विस व गैस",500,1200,"unit"),
    ("fridge-washing-machine","appliance","Fridge / Washing Machine Fix","फ्रिज / वॉशिंग मशीन",400,1000,"visit"),
    ("outstation-trip","driver","Outstation Trip (per day)","बाहर यात्रा (प्रति दिन)",2000,3500,"day"),
    ("local-hourly","driver","Local Hourly Driving","लोकल प्रति घंटा",250,400,"hour"),
    ("garden-upkeep","gardener","Monthly Garden Upkeep","मासिक बगिया देखभाल",1000,2500,"month"),
    ("plant-trimming","gardener","Plant Trimming & Manure","कटाई व खाद",300,700,"visit"),
    ("daily-tiffin","cook","Daily Tiffin Cooking","डेली टिफिन",3000,6000,"month"),
    ("party-cooking","cook","Party Cooking (per day)","पार्टी कुकिंग (दिन)",1200,2500,"day"),
    ("elder-daycare","caregiver","Elder Day Care","बुज़ुर्ग देखभाल",600,1000,"day"),
    ("patient-attendant","caregiver","Patient Attendant (12h)","मरीज़ सहायक (12 घंटे)",800,1400,"shift"),
    ("cockroach-treatment","pest","Cockroach Treatment","कॉकरोच ट्रीटमेंट",800,1800,"home"),
    ("termite-treatment","pest","Termite Treatment","दीमक ट्रीटमेंट",2500,6000,"home"),
]

FIRST_NAMES_M = ["Ramesh","Suresh","Mohd Imran","Vijay","Ashok","Deepak","Sanjay","Rafiq","Babulal","Jagdish","Mukesh","Shyam","Iqbal","Ramkishun","Omprakash","Devendra"]
FIRST_NAMES_F = ["Sunita","Rehana","Kiran","Meena","Fatima","Anita","Geeta","Shabana","Pushpa","Nisha","Radha","Munni"]

# Worker photos: FairFace dataset (Indian-only split), visually curated for
# quality (frontal, well-lit, adult). m01 = Ramesh's photo, also the hero shot.
PHOTO_POOL = {
    "men": [f"/static/img/m{i:02d}.jpg" for i in range(2, 35)],
    "women": [f"/static/img/f{i:02d}.jpg" for i in range(1, 27)],
}
LAST_NAMES = ["Kumar","Yadav","Sharma","Ansari","Verma","Singh","Prasad","Khan","Gupta","Pal","Chauhan","Mahto"]

PBKDF2_ROUNDS = 210_000   # ~90 ms/login on this class of VPS (measured); legacy hashes upgrade on login

def hash_pw(pw: str) -> str:
    """PBKDF2-SHA256 with a per-user random salt.
    Format: pbkdf2_sha256$<rounds>$<salt_hex>$<dk_hex>"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${dk.hex()}"

def _hash_pw_legacy(pw: str) -> str:
    """Old single-round SHA-256 format, kept ONLY to verify + upgrade existing rows."""
    return hashlib.sha256(("ss$" + pw + "$salt").encode()).hexdigest()

_dummy_hash = None

def verify_pw(pw: str, stored: str):
    """Constant-time password check. Returns (ok, needs_upgrade)."""
    if not stored:
        return False, False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt, want = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(rounds))
            return hmac.compare_digest(dk.hex(), want), False
        except (ValueError, TypeError):
            return False, False
    ok = hmac.compare_digest(_hash_pw_legacy(pw), stored)
    return ok, ok     # legacy match -> caller re-hashes with PBKDF2

def dummy_verify(pw: str):
    """Burn the same PBKDF2 work for unknown phone numbers (no timing oracle)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_pw("dummy-password-not-a-real-user")
    verify_pw(pw, _dummy_hash)

def get_db():
    """Single shared connection guarded by a lock - avoids SQLite lock contention
    between FastAPI threadpool workers entirely."""
    global _conn
    with _db_lock:
        if _conn is None:
            os.makedirs(DATA_DIR, exist_ok=True)
            _conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys=ON")
            try:
                _conn.execute("PRAGMA journal_mode=WAL")
                _conn.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass
        return _conn

DB_LOCK = _db_lock

def init_db(force=False):
    """Idempotent bootstrap: creates + seeds the DB when missing, then always applies
    schema migrations. Returns True when it seeded a fresh database.
    NOTE: never closes the shared connection - the old build closed it after seeding,
    which broke every subsequent query in the same process."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    fresh = not os.path.exists(DB_PATH)
    conn = get_db()
    if fresh:
        c = conn.cursor()
        c.executescript("""
    CREATE TABLE users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('customer','worker','federation_admin','super_admin','coop_admin')),
        preferred_language TEXT DEFAULT 'hi',
        coop_id INTEGER REFERENCES cooperatives(id),
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE federations(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, state TEXT);
    CREATE TABLE cooperatives(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, federation_id INTEGER REFERENCES federations(id),
        zone TEXT NOT NULL, district TEXT DEFAULT 'Delhi'
    );
    CREATE TABLE workers(
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        coop_id INTEGER REFERENCES cooperatives(id),
        trade TEXT NOT NULL, exp_years INTEGER, bio TEXT,
        photo TEXT, hourly_min INTEGER, hourly_max INTEGER,
        rating_avg REAL DEFAULT 0, rating_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','verified','suspended')),
        zone TEXT, lat REAL, lng REAL, radius_km REAL DEFAULT 8,
        e_shram_uan TEXT, jobs_done INTEGER DEFAULT 0
    );
    CREATE TABLE certifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER REFERENCES workers(user_id),
        title TEXT NOT NULL, issuer TEXT, year INTEGER, verified_by_coop INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending'
    );
    CREATE TABLE services(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE, trade TEXT, name_en TEXT, name_hi TEXT,
        pmin INTEGER, pmax INTEGER, unit TEXT
    );
    CREATE TABLE bookings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE, customer_id INTEGER REFERENCES users(id),
        worker_id INTEGER REFERENCES users(id), service_id INTEGER REFERENCES services(id),
        scheduled_for TEXT, address TEXT, zone TEXT, notes TEXT,
        is_emergency INTEGER DEFAULT 0,
        status TEXT DEFAULT 'requested' CHECK(status IN ('requested','accepted','enroute',
            'in_progress','completed','cancelled')),
        price INTEGER, payment_status TEXT DEFAULT 'none'
            CHECK(payment_status IN ('none','paid')),
        created_at TEXT DEFAULT (datetime('now')),
        completed_at TEXT
    );
    CREATE TABLE payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER UNIQUE REFERENCES bookings(id),
        amount INTEGER, commission INTEGER, net INTEGER,
        method TEXT DEFAULT 'demo_upi', gateway_ref TEXT, status TEXT DEFAULT 'success',
        paid_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER UNIQUE REFERENCES bookings(id),
        customer_id INTEGER, worker_id INTEGER,
        rating INTEGER CHECK(rating BETWEEN 1 AND 5), comment TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE welfare(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER REFERENCES workers(user_id),
        scheme TEXT CHECK(scheme IN ('PMSBY','PMJJBY')),
        enrolled_on TEXT, valid_till TEXT, status TEXT DEFAULT 'active',
        requested_by TEXT DEFAULT 'admin', requested_on TEXT, decided_by TEXT
    );
    CREATE TABLE welfare_claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER REFERENCES workers(user_id),
        scheme TEXT, reason TEXT DEFAULT '', amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'filed',
        created_at TEXT DEFAULT (datetime('now')),
        decided_at TEXT, decided_by TEXT
    );
    CREATE TABLE payout_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period_start TEXT, period_end TEXT, total_net INTEGER, total_commission INTEGER,
        worker_count INTEGER, job_count INTEGER, status TEXT DEFAULT 'executed',
        created_by TEXT, created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE sessions(token TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
    """)
        _seed(c)
        conn.commit()
    ensure_schema(conn)
    return fresh


def _add_col(conn, table, col, decl):
    """SQLite has no ADD COLUMN IF NOT EXISTS - check first, stay idempotent."""
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in have:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _migrate_users_role(conn):
    """Widen users.role to allow 'coop_admin' (cooperative-society logins) and add
    users.coop_id. SQLite cannot ALTER a CHECK constraint, so the table is rebuilt
    copy-first with a row-count gate - the old table is only dropped after the copy
    is verified, and a count mismatch aborts instead of leaving a half-migrated DB."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not row or "'coop_admin'" in row[0]:
        _add_col(conn, "users", "coop_id", "INTEGER REFERENCES cooperatives(id)")
        return False
    before = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript("""
    CREATE TABLE users_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('customer','worker','federation_admin','super_admin','coop_admin')),
        preferred_language TEXT DEFAULT 'hi',
        coop_id INTEGER REFERENCES cooperatives(id),
        created_at TEXT DEFAULT (datetime('now'))
    );
    INSERT INTO users_new(id,phone,password_hash,name,role,preferred_language,created_at)
        SELECT id,phone,password_hash,name,role,preferred_language,created_at FROM users;
    DROP TABLE users;
    ALTER TABLE users_new RENAME TO users;
    """)
    after = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if after != before:
        raise RuntimeError(f"users rebuild lost rows ({before} -> {after}) - aborting, old table intact")
    conn.execute("PRAGMA foreign_keys=ON")
    return True


def _ensure_coop_admins(conn):
    """One society login per cooperative. The PS makes Labour Cooperative Societies
    co-owners of the platform, so each samiti gets a scoped dashboard for its own
    workers, verifications and welfare - not a view of the whole federation."""
    rows = conn.execute("""SELECT c.id, c.name FROM cooperatives c
                           WHERE NOT EXISTS (SELECT 1 FROM users u
                                             WHERE u.role='coop_admin' AND u.coop_id=c.id)""").fetchall()
    made = []
    for cid, cname in rows:
        phone = str(7000000100 + cid)
        if conn.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            continue
        conn.execute("""INSERT INTO users(phone,password_hash,name,role,preferred_language,coop_id)
                        VALUES(?,?,?,'coop_admin','hi',?)""",
                     (phone, hash_pw("admin123"), f"{cname} - Samiti Admin", cid))
        made.append((cid, phone))
    return made


def ensure_schema(conn=None):
    """Idempotent migrations - safe on a fresh DB and on the existing live one.
    Adds the decline ledger (worker agency), the booking event log (so customers can
    SEE what happened to their booking) and the payout ledger + indexes for the hot
    query paths."""
    conn = conn if conn is not None else get_db()
    with _db_lock:
        conn.executescript("""
    CREATE TABLE IF NOT EXISTS declines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER REFERENCES bookings(id),
        worker_id INTEGER REFERENCES workers(user_id),
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(booking_id, worker_id)
    );
    CREATE TABLE IF NOT EXISTS booking_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER REFERENCES bookings(id),
        kind TEXT NOT NULL,
        detail TEXT DEFAULT '',
        actor TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_booking_events_bid ON booking_events(booking_id, id);
    CREATE TABLE IF NOT EXISTS payout_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER REFERENCES payout_runs(id),
        booking_id INTEGER REFERENCES bookings(id) UNIQUE,
        worker_id INTEGER,
        net INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_bookings_worker_status ON bookings(worker_id, status);
    CREATE INDEX IF NOT EXISTS idx_bookings_customer ON bookings(customer_id, id DESC);
    CREATE INDEX IF NOT EXISTS idx_bookings_sched ON bookings(scheduled_for);
    CREATE INDEX IF NOT EXISTS idx_workers_trade_zone ON workers(trade, zone, status);
    CREATE INDEX IF NOT EXISTS idx_reviews_worker ON reviews(worker_id);
    """)
        # ---- society access + certification trail + welfare workflow (SIH26089 clauses) ----
        _migrate_users_role(conn)
        _add_col(conn, "certifications", "status", "TEXT DEFAULT 'pending'")
        for _col, _decl in (("requested_by", "TEXT DEFAULT 'admin'"), ("requested_on", "TEXT"),
                            ("decided_by", "TEXT")):
            _add_col(conn, "welfare", _col, _decl)
        conn.executescript("""
    CREATE TABLE IF NOT EXISTS welfare_claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER REFERENCES workers(user_id),
        scheme TEXT, reason TEXT DEFAULT '', amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'filed',
        created_at TEXT DEFAULT (datetime('now')),
        decided_at TEXT, decided_by TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_welfare_claims_worker ON welfare_claims(worker_id, id DESC);
    """)
        # certificates the cooperative blessed at approval time are already verified
        conn.execute("""UPDATE certifications SET status='verified'
                        WHERE verified_by_coop=1 AND status!='verified'""")
        _ensure_coop_admins(conn)
        conn.commit()

def _seed(c):
    rng = random.Random(26089)
    today = date.today()

    # ---- org structure ----
    c.execute("INSERT INTO federations(name,state) VALUES(?,?)",
              ("Delhi Labour Cooperative Federation","Delhi"))
    fed_id = c.lastrowid
    coops = []
    for i,(zk,zname,zhi,_,_) in enumerate(ZONES[:8]):
        cname = f"{zname} Shramik Sahkari Samiti"
        c.execute("INSERT INTO cooperatives(name,federation_id,zone,district) VALUES(?,?,?,'Delhi')",
                  (cname, fed_id, zk))
        coops.append((c.lastrowid, zk))

    # ---- services ----
    for row in SERVICES:
        c.execute("INSERT INTO services(slug,trade,name_en,name_hi,pmin,pmax,unit) VALUES(?,?,?,?,?,?,?)", row)

    # ---- demo accounts ----
    demo_users = [
        ("9000000001","demo123","Priya Sharma","customer","en"),   # demo customer
        ("8000000001","demo123","Ramesh Kumar","worker","hi"),      # demo worker (electrician)
        ("7000000001","admin123","Sh. O.P. Meena (IFS)","federation_admin","en"),
    ]
    for phone,pw,nm,role,lang in demo_users:
        c.execute("INSERT INTO users(phone,password_hash,name,role,preferred_language) VALUES(?,?,?,?,?)",
                  (phone,hash_pw(pw),nm,role,lang))

    priya_id = 1; ramesh_uid = 2; admin_uid = 3
    # Ramesh = verified electrician in Seelampur
    c.execute("""INSERT INTO workers(user_id,coop_id,trade,exp_years,bio,photo,hourly_min,hourly_max,
                 rating_avg,rating_count,status,zone,lat,lng,e_shram_uan,jobs_done)
                 VALUES(2,1,'electrician',12,'12 saal ka tajurba. Ghar wiring, MCB, motor repair. Delhi Electricity Board ke saath 3 saal contractor bhi raha.',
                 '/static/img/m01.jpg',250,500,4.7,63,'verified','east',28.6702,77.2674,'1234-5678-9012',187)""")
    certs_r = [("ITI Electrician Certificate","NCVT, Delhi",2014),("Domestic Wiring Level-2","Skill India",2019)]
    for t,i,y in certs_r:
        c.execute("INSERT INTO certifications(worker_id,title,issuer,year,verified_by_coop) VALUES(2,?,?,?,1)",(t,i,y))

    # ---- 59 more workers ----
    uid = 4  # next user id after 3 seeded
    worker_pool = []  # (uid, trade, zone, status)
    worker_pool.append((ramesh_uid, "electrician", "east", "verified"))  # Ramesh earns real history too
    # photo pools are exact-size, so split genders deterministically:
    # 26 women + 33 men = 59 loop workers (+Ramesh = 60 total)
    genders = ["women"]*len(PHOTO_POOL["women"]) + ["men"]*len(PHOTO_POOL["men"])
    rng.shuffle(genders)
    for wi in range(59):
        trade_idx = wi % len(TRADES)
        coop_id, zkey = coops[wi % len(coops)]
        # pin MUST live in the worker's labelled zone (matcher filters by distance)
        _,_,_,lat,lng = next(z for z in ZONES if z[0] == zkey)
        gender = genders[wi]
        nm = f"{rng.choice(FIRST_NAMES_F if gender=='women' else FIRST_NAMES_M)} {rng.choice(LAST_NAMES)}"
        phone = f"98{rng.randrange(10000000,99999999)}"[:10]
        while True:
            try:
                c.execute("INSERT INTO users(phone,password_hash,name,role,preferred_language) VALUES(?,?,?,'worker',?)",
                          (phone,hash_pw("worker@2026"),nm,rng.choice(["hi","en"])))
                break
            except sqlite3.IntegrityError:
                phone = str(rng.randrange(9000000000,9999999999))
        this_uid = c.lastrowid
        exp = rng.randint(2,22)
        status = "verified" if rng.random() < 0.82 else "pending"
        gender_key = "women" if gender == "women" else "men"
        pool = PHOTO_POOL[gender_key]
        photo_i = rng.randrange(len(pool))
        photo = pool.pop(photo_i)  # unique: each photo used at most once
        base_lo, base_hi = {"electrician":(220,480),"plumber":(200,420),"carpenter":(280,550),"painter":(240,460),
                            "cleaning":(180,320),"appliance":(260,520),"driver":(240,380),"gardener":(170,300),
                            "cook":(200,360),"caregiver":(280,520),"pest":(250,480)}[TRADES[trade_idx][0]]
        c.execute("""INSERT INTO workers(user_id,coop_id,trade,exp_years,bio,photo,hourly_min,hourly_max,
                     status,zone,lat,lng,e_shram_uan,jobs_done)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'2345-6789-01'||?,?)""",
                  (this_uid, coop_id, TRADES[trade_idx][0], exp,
                   f"{exp} saal ka tajurba. Cooperatives se certified.",
                   f"{photo}", base_lo, base_hi, status,
                   zkey, lat+(rng.random()-0.5)*0.02, lng+(rng.random()-0.5)*0.02,
                   f"{rng.randrange(100,999)}", rng.randint(5,210)))
        if rng.random() < 0.55:
            cert_titles = {"electrician":("ITI Electrician","NCVT"),"plumber":("Plumbing Level-1","NSDC"),
                "carpenter":("Carpentry Craft","ITI"),"painter":("Painting & Decor","NSDC"),
                "cleaning":("Housekeeping Pro","Skill India"),"appliance":("AC Technician","CDC India"),
                "driver":("Driving Licence Commercial","DL Transport Dept."),"gardener":("Horticulture Helper","Khadi Board"),
                "cook":("Food Handling Cert","FSSAI"),"caregiver":("Home Health Aide","Red Cross"),
                "pest":("Pest Control Operator","CIB&RC")}
            ct, ci = cert_titles[TRADES[trade_idx][0]]
            c.execute("INSERT INTO certifications(worker_id,title,issuer,year,verified_by_coop) VALUES(?,?,?,?,?)",
                      (this_uid,ct,ci,rng.randint(2012,2024),1 if status=="verified" else 0))
        worker_pool.append((this_uid, TRADES[trade_idx][0], zkey, status))

    # ---- welfare enrolments ----
    for wid,_,_,status in worker_pool:
        if status=="verified":
            schemes = []
            if rng.random()<0.85: schemes.append("PMSBY")
            if rng.random()<0.55: schemes.append("PMJJBY")
            yr = today.year
            for s in schemes:
                c.execute("INSERT INTO welfare(worker_id,scheme,enrolled_on,valid_till,status) VALUES(?,?,?,?,'active')",
                          (wid,s,f"{yr}-04-01",f"{yr+1}-03-31"))
    if not c.execute("SELECT 1 FROM welfare WHERE worker_id=2 AND scheme='PMSBY'").fetchone():
        c.execute("INSERT INTO welfare(worker_id,scheme,enrolled_on,valid_till,status) VALUES(2,'PMSBY',?,?,'active')",
                  (f"{today.year}-04-01",f"{today.year+1}-03-31"))

    # ---- 180 days of bookings with seasonality ----
    # weight per trade by month (index=calendar month): cleaning+ Diwali, appliance+ summer
    def month_weight(trade, m):
        w = 1.0
        if trade=="cleaning" and m in (10,11): w += 2.2   # pre-Diwali deep clean
        if trade=="electrician" and m in (10,11): w += 1.2  # festive lights/faults
        if trade=="appliance" and m in (4,5,6): w += 2.4   # AC summer surge
        if trade=="cook" and m in (3,11): w += 1.0         # wedding/festive season
        if trade in ("painter",) and m in (2,3,10): w += 0.8
        return w
    svc_rows = c.execute("SELECT id,slug,trade,pmin,pmax FROM services").fetchall()
    cust_ids = [priya_id]
    # extra background customers
    for k in range(14):
        ph = f"91{k:08d}"
        c.execute("INSERT INTO users(phone,password_hash,name,role) VALUES(?,?,?,'customer')",
                  (ph,hash_pw("cust@2026"),f"{rng.choice(FIRST_NAMES_M)} {rng.choice(LAST_NAMES)}"))
        cust_ids.append(c.lastrowid)

    COMMENTS = ["Kaam badhiya tha, time pe aaye.","Very professional, cleaned up after work.",
        "Fair rate, no bargaining drama.","Achha kaam, dobara bulaaunga.",
        "Fixed the issue quickly. Recommended.","Polite and skilled.",
        "Rate thoda zyada laga par quality solid thi.","On time, did exactly what was promised.",
        "Bahut badhiya kaam, bilkul time pe.","Perfect kaam — area bhi saaf chhoda.",
        "Ekdam professional tareeke se kaam kiya.","Rate bhi sahi, quality bhi top.",
        "Dobara zaroor bulaaunga. Highly recommended.","Problem jad se theek ho gayi.",
        "Family ke saath bilkul bharosa kar sakte hain.","Itne acche mistri mushkil se milte hain.",
        "Same day fix kar diya, zabardast.","Kaam accha tha, thoda late pahunche.",
        "Quality solid, rate thoda zyada laga.","Badhiya kaam, baat karne mein thoda jaldi tha.",
        "Kaam sahi hua, tools pehle se ready nahi the.","Time pe nikle, kaam badiya.",
        "Accha kaam, dobara inhi ko bulaungi.","Kaam ho gaya, par do visit lage.",
        "Theek-thaak. Koi khaas baat nahi.","Average. Rate ke hisaab se expect zyada tha."]
    n_bookings = 0
    max_weight = max(month_weight(t, m) for t in set(s[2] for s in SERVICES) for m in range(1, 13))
    d0 = today - timedelta(days=181)
    codeset = set()
    for dd in range(181):
        day = d0 + timedelta(days=dd)
        dow = day.weekday()
        m = day.month
        day_total = rng.gauss(16 + dow*1.8, 4)  # weekend-heavy
        day_total = max(4, int(day_total))
        for _ in range(day_total):
            svc_id, slug, trade, lo, hi = svc_rows[rng.randrange(len(svc_rows))]
            cand = [wp for wp in worker_pool if wp[1]==trade and wp[3]=="verified"]
            if not cand:
                continue
            wuid,_,wzone,_ = cand[rng.randrange(len(cand))]
            # seasonal filter: off-season trades get dropped more often
            keep_prob = min(1.0, month_weight(trade, m) / max_weight * 2.2)
            if rng.random() > keep_prob:
                continue
            cust = rng.choice(cust_ids)
            price = int(rng.uniform(lo,hi)//10*10)
            code = f"SS{day.strftime('%y%m%d')}{n_bookings+1:04d}"
            while code in codeset: code += "X"
            codeset.add(code)
            sched = datetime(day.year,day.month,day.day,rng.choice([9,10,11,12,14,15,16,17]),rng.choice([0,30]))
            done = sched + timedelta(hours=rng.randint(1,4))
            if done.date() >= today: continue  # only past-completed for history
            st = "completed"
            c.execute("""INSERT INTO bookings(code,customer_id,worker_id,service_id,scheduled_for,address,zone,
                         notes,is_emergency,status,price,payment_status,created_at,completed_at)
                         VALUES(?,?,?,?,?,?,?,?,0,?,?,'paid',?,?)""",
                      (code,cust,wuid,svc_id,sched.isoformat(),
                       f"House {rng.randint(1,180)}, {rng.choice([z[1] for z in ZONES])} Phase {rng.randint(1,4)}",
                       wzone,"Seed history",st,price,sched.isoformat(),done.isoformat()))
            bid = c.lastrowid
            comm = int(price*COMMISSION_PCT/100)
            c.execute("INSERT INTO payments(booking_id,amount,commission,net,gateway_ref,paid_at) VALUES(?,?,?,?,?,?)",
                      (bid,price,comm,price-comm,f"DEMOUPI{rng.randrange(10**9,10**10)}",sched.isoformat()))
            if rng.random() < 0.62:
                rt = rng.choices([5,4,3],[0.62,0.28,0.10])[0]
                cm = rng.choice(COMMENTS) if rng.random()<0.45 else ""
                c.execute("INSERT INTO reviews(booking_id,customer_id,worker_id,rating,comment,created_at) VALUES(?,?,?,?,?,?)",
                          (bid,cust,wuid,rt,cm,sched.isoformat()))
            c.execute("UPDATE workers SET jobs_done=jobs_done+1 WHERE user_id=?", (wuid,))
            n_bookings += 1

    # recompute ratings from reviews
    c.execute("""UPDATE workers SET 
                 rating_avg=COALESCE((SELECT ROUND(AVG(rating),1) FROM reviews WHERE reviews.worker_id=workers.user_id),0),
                 rating_count=(SELECT COUNT(*) FROM reviews WHERE reviews.worker_id=workers.user_id)""")

    # ---- live demo bookings (today/tomorrow) for the three demo personas ----
    tmr = (today + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
    svc_plumb = c.execute("SELECT id FROM services WHERE slug='tap-leak-fix'").fetchone()
    # a plumber near Priya (Lajpat Nagar) requested->accepted for tracking demo
    plumbers = [wp for wp in worker_pool if wp[1]=="plumber" and wp[3]=="verified"]
    plumb_uid = plumbers[0][0] if plumbers else None
    c.execute("""INSERT INTO bookings(code,customer_id,worker_id,service_id,scheduled_for,address,zone,
                 notes,is_emergency,status,price,created_at)
                 VALUES(?,?,?,?,?,?,?, 'Kitchen tap leaking badly',0,'accepted',350,?)""",
              ("SS-LIVE-01",priya_id,plumb_uid,svc_plumb["id"],tmr,
               "B-42, Lajpat Nagar-II, New Delhi","south",datetime.now().isoformat()))
    # one pending verification case for admin queue
    pend = [wp for wp in worker_pool if wp[3]=="pending"][:3]

    # ---- payout run history (last 4 weeks) ----
    for wk in range(4):
        end = today - timedelta(days=wk*7)
        start = end - timedelta(days=7)
        rows = c.execute("""SELECT COUNT(*) jc, SUM(commission) tc, SUM(net) tn, COUNT(DISTINCT worker_id) wc
                            FROM payments p JOIN bookings b ON b.id=p.booking_id
                            WHERE date(b.scheduled_for)>=? AND date(b.scheduled_for<?)""",(start.isoformat(),end.isoformat())).fetchone()
        if rows["jc"]:
            c.execute("""INSERT INTO payout_runs(period_start,period_end,total_net,total_commission,worker_count,job_count,status,created_by)
                         VALUES(?,?,?,?,?,?,?,'O.P. Meena')""",
                      (start.isoformat(),end.isoformat(),rows["tn"],rows["tc"],rows["wc"],rows["jc"],"executed"))
    print(f"[seed] workers={len(worker_pool)+1} bookings_180d={n_bookings} zones={len(ZONES)} services={len(SERVICES)}")

if __name__ == "__main__":
    created = init_db(force=True)
    print("DB created & seeded." if created else "DB already exists.")
