"""Print engine results for recent days from a local data directory (DATA_DIR=... python -m scripts.engine_report [day])."""
import json
import sys
from datetime import date, timedelta

from backend import db, engine, google_data
from backend.models import Profile
from backend.scores import daily

p = Profile.model_validate(db.get("profile"))
on = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
start = (date.fromisoformat(on) - timedelta(days=95)).isoformat()
after = (date.fromisoformat(on) + timedelta(days=1)).isoformat()
entries = db.entries(start, on)
days = daily(entries)
hr = google_data.minutes("heart-rate-minutes", start, after)
st = google_data.minutes("steps-minutes", start, after)
ms = google_data.summaries(start, on)
for d in [(date.fromisoformat(on) - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]:
    r = engine.compute(days, entries, p, d, hr, st, ms, detail=False)
    s = r["sleep"] or {}
    st_ = r["stress"] or {}
    print(d, "strain", (r["strain"] or {}).get("score"), "rec", r["recovery"]["score"], "sleep", s.get("score"), s.get("parts"), "bank", s.get("bank"),
          "stress", [st_.get(k) for k in ("high", "low", "average", "current")], "energy", (r["energy"] or {}).get("current"), "target", r["target"], "rhr", r["rhr"])
r = engine.compute(days, entries, p, on, hr, st, ms)
print(json.dumps({k: r[k] for k in ("zones", "zone_ranges", "vo2_estimate", "monitor")}, default=str)[:1500])
print(json.dumps(r["sessions"], default=str)[:1500])
print(json.dumps({k: {kk: v for kk, v in r["load"][k].items() if kk != "history"} for k in r["load"]}))
print(json.dumps(r["recovery"]))
for g, items in r["trends"].items():
    print(g, [(t["label"], t["value"], t["status"], len(t["points"])) for t in items])

from backend import bioage  # noqa: E402

eng = engine.Engine(days, entries, p, on, hr, st, ms)
b = bioage.biological_age(eng, entries, p, on)
print("BIO", {k: b.get(k) for k in ("available", "as_of", "chronological", "biological", "difference", "confidence", "change", "next_update_days", "data_days", "history")})
for c in b.get("categories", {}).values():
    print(" ", c["label"], c["years"], [(f["label"], f["value"], f["years"], f["confidence"]) for f in c["factors"]])
