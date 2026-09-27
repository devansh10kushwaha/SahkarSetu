"""Demand forecasting - explainable weekly-seasonality model.
Method: day-of-week median counts (last 8 weeks) x trend ratio (recent 14d vs prior 14d).
Deliberately simple so a judge can verify it on one slide.
"""
import time as _time
from datetime import date, timedelta
import sqlite3
from db import get_db, DB_LOCK, ZONES, TRADES

DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# The admin page calls /forecast and /forecast/summary back-to-back; without a
# short TTL the (identical) model was computed twice per page load.
_CACHE = {}
_CACHE_TTL = 30.0

def compute_forecast(zone=None, trade=None, use_cache=True):
    """Returns rows: [{zone, trade, dow, date, predicted, recent_avg, workers_available, suggest}]"""
    ck = (zone, trade)
    if use_cache:
        hit = _CACHE.get(ck)
        if hit and _time.time() - hit[0] < _CACHE_TTL:
            return hit[1]
    with DB_LOCK:
        conn = get_db()
        rows = conn.execute("""
            SELECT date(b.scheduled_for) d, b.zone z, s.trade t, COUNT(*) n
            FROM bookings b JOIN services s ON s.id=b.service_id
            WHERE b.status='completed' AND date(b.scheduled_for) >= date('now','-56 days')
            GROUP BY d, z, t
        """).fetchall()
        # one grouped query instead of one COUNT per zone x trade pair (was 110 queries)
        avail_map = {(r["trade"], r["zone"]): r["n"] for r in conn.execute(
            "SELECT trade, zone, COUNT(*) n FROM workers WHERE status='verified' GROUP BY trade, zone").fetchall()}

    hist = {}   # (zone,trade,date) -> n
    # every zone x trade pair renders (zero-history zones show ~0 honestly)
    pairs = {(z[0], t[0]) for z in ZONES for t in TRADES}
    for r in rows:
        if zone and r["z"] != zone: continue
        if trade and r["t"] != trade: continue
        hist[(r["z"], r["t"], r["d"])] = r["n"]
        pairs.add((r["z"], r["t"]))

    today = date.today()
    results = []
    for (zk, tk) in sorted(pairs):
        # daily counts oldest -> newest
        series = [hist.get((zk, tk, (today - timedelta(days=i)).isoformat()), 0)
                  for i in range(56, 0, -1)]
        # day-of-week medians over the window
        dow_vals = {i: [] for i in range(7)}
        for i, n in enumerate(series):
            dt = today - timedelta(days=len(series) - i)
            dow_vals[dt.weekday()].append(n)
        dow_med = {}
        for i, vals in dow_vals.items():
            vals.sort()
            m = len(vals)
            dow_med[i] = (vals[m//2] if m % 2 else (vals[m//2-1]+vals[m//2])/2) if vals else 0
        # trend ratio: last 14d vs previous 14d
        rec = sum(series[-14:]) / 14.0
        pri = (sum(series[-28:-14]) / 14.0) or 0.001
        trend = max(0.5, min(1.6, rec / pri))

        # available verified workers of this trade in this zone
        avail = avail_map.get((tk, zk), 0)

        for k in range(1, 8):
            dt = today + timedelta(days=k)
            base = dow_med[dt.weekday()]
            pred = round(base * trend, 1)
            row = {
                "zone": zk, "trade": tk,
                "date": dt.isoformat(), "dow": DOW_NAMES[dt.weekday()],
                "predicted": pred, "workers_available": avail,
                "suggest": None,
            }
            if pred >= 1.5 and pred > avail * 1.4:
                row["suggest"] = f"Add ~{max(1, round(pred - avail))} more {tk}(s)"
            results.append(row)
    out = {"model": "weekly-seasonality x 14-day trend ratio",
           "window": "56 days history", "rows": results}
    _CACHE[ck] = (_time.time(), out)
    return out

def forecast_summary():
    """Top suggestions only - for the admin headline panel."""
    fc = compute_forecast()
    sug = [r for r in fc["rows"] if r["suggest"]]
    sug.sort(key=lambda r: -r["predicted"])
    return {"model": fc["model"], "top": sug[:12], "total_signals": len(sug)}
