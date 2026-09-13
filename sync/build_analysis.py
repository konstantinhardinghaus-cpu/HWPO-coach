"""
Trainingsanalyse -- rechnet aus den gecachten Rohdaten (sync/cache/*.json)
die komplette Seite neu und schreibt ../trainingsanalyse.html.

Siehe README.md fuer den Gesamtablauf und die Formeln.
Diese Datei ist die massgebliche Quelle der Formeln -- wer eine Konstante
aendert, aendert damit auch, was auf der Seite steht.
"""
import json, math, datetime, statistics, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

# ---------------------------------------------------------------------------
# Konstanten -- hier aendern, wenn sich die Grundlage aendert, und in der
# README dazuschreiben, warum.
# ---------------------------------------------------------------------------
RHR = 46.0          # 10.-Perzentil-Baseline aus Apple-Health- + Garmin-Ruhepuls
HRMAX = 197         # gemessen 18.08.2026, >=60s gehalten (siehe README)
ATHLETE_GENDER = "M"  # aus dem Vornamen abgeleitet, nicht bestaetigt
JUNK_MIN_DURATION_S = 60      # Einheiten darunter gelten als Fehlstart/Test
DUP_MATCH_TOLERANCE_S = 5     # Toleranz beim Garmin<->AppleHealth-Abgleich
DUP_TYPES = {"Cycling", "Rowing", "TraditionalStrengthTraining"}
M_PACE_S_KM = 339.1            # Marathon-Renn-Aequivalent aus VDOT (Schwelle fuer "locker")


def trimp_weight(hr_i):
    hr_i = max(0.0, min(1.0, hr_i))
    if ATHLETE_GENDER == "M":
        return hr_i * 0.64 * math.exp(1.92 * hr_i)
    return hr_i * 0.86 * math.exp(1.67 * hr_i)


def pct(vals, p):
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return vals[int(k)]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def load_cache(name, default):
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def to_date(iso):
    return iso[:10]


def ah_laps(w):
    """Runden/Splits einer Apple-Health-Einheit als (dauer_s, avg_hr)-Liste."""
    if w.get("laps"):
        segs = [(l["durationSec"], l["avgHr"]) for l in w["laps"] if l.get("avgHr") and l.get("durationSec")]
        if segs:
            return segs
    if w.get("splits"):
        segs = [(s["durationSec"], s["avgHr"]) for s in w["splits"] if s.get("avgHr") and s.get("durationSec")]
        if segs:
            return segs
    if w.get("avgHr") and w.get("durationSec"):
        return [(w["durationSec"], w["avgHr"])]
    return []


def build_canonical_activities(ah_workouts, garmin_activities, garmin_period_start):
    """
    ah_workouts: Liste von apple_health_get_workouts()-Eintraegen (alle Quellen)
    garmin_activities: Liste von garmin_get_activities()-Eintraegen ab garmin_period_start
    garmin_period_start: ab diesem Datum gilt Garmin als alleinige Quelle (siehe README)
    """
    garmin_deviceless = [g for g in garmin_activities if "deviceName" not in g]
    garmin_real = [g for g in garmin_activities if g.get("deviceName")]

    matched = {}
    for w in ah_workouts:
        d = to_date(w["startDate"])
        if not (garmin_period_start <= d < garmin_real[0]["local_date"] if garmin_real else False):
            pass
        if w["activityType"] not in DUP_TYPES:
            continue
        dur = w.get("durationSec", 0)
        for g in garmin_deviceless:
            if g["local_date"] == d and abs(g["durationInSeconds"] - dur) <= DUP_MATCH_TOLERANCE_S:
                matched[w["uuid"]] = g
                break

    canon = []
    garmin_real_dates = sorted(g["local_date"] for g in garmin_real) if garmin_real else []
    garmin_real_start = garmin_real_dates[0] if garmin_real_dates else "9999-99-99"

    for w in ah_workouts:
        d = to_date(w["startDate"])
        if d >= garmin_real_start:
            continue  # ab hier ist Garmin allein zustaendig (Doppelzaehlung sonst)
        if w.get("durationSec", 0) < JUNK_MIN_DURATION_S:
            continue
        if w["uuid"] in matched:
            g = matched[w["uuid"]]
            canon.append(dict(id=str(g["activityId"]), date=d, sport=g["activityType"],
                               duration_s=g["durationInSeconds"], distance_m=g.get("distanceInMeters"),
                               avg_hr=g.get("averageHeartRateInBeatsPerMinute"),
                               max_hr=g.get("maxHeartRateInBeatsPerMinute"),
                               laps=[(g["durationInSeconds"], g.get("averageHeartRateInBeatsPerMinute"))],
                               source="garmin(matched)", garmin_load=g.get("activityTrainingLoad"), splits=None))
        else:
            canon.append(dict(id=w["uuid"], date=d, sport=w["activityType"], duration_s=w.get("durationSec", 0),
                               distance_m=w.get("distanceMeters"), avg_hr=w.get("avgHr"), max_hr=w.get("maxHr"),
                               laps=ah_laps(w), source="apple_health", splits=w.get("splits")))

    for g in garmin_real:
        if g.get("durationInSeconds", 0) < JUNK_MIN_DURATION_S:
            continue
        laps = [(g["durationInSeconds"], g.get("averageHeartRateInBeatsPerMinute"))]
        canon.append(dict(id=str(g["activityId"]), date=g["local_date"], sport=g["activityType"],
                           duration_s=g["durationInSeconds"], distance_m=g.get("distanceInMeters"),
                           avg_hr=g.get("averageHeartRateInBeatsPerMinute"),
                           max_hr=g.get("maxHeartRateInBeatsPerMinute"), laps=laps, source="garmin(real)",
                           garmin_load=g.get("activityTrainingLoad"), splits=None, name=g.get("activityName")))

    return canon


def compute_trimp(canon):
    for c in canon:
        if not c.get("avg_hr"):
            c["trimp"] = None
            continue
        total = 0.0
        for dur, hr in c["laps"]:
            if hr is None:
                continue
            hr_i = (hr - RHR) / (HRMAX - RHR)
            total += trimp_weight(hr_i) * dur
        c["trimp"] = total / 60.0
    return canon


def compute_belastung(canon):
    daily_trimp = defaultdict(float)
    for c in canon:
        if c["trimp"]:
            daily_trimp[c["date"]] += c["trimp"]
    active_vals = list(daily_trimp.values())
    anchor = max(pct(active_vals, 0.95), 40) if active_vals else 40
    for c in canon:
        c["belastung"] = 100 * c["trimp"] / anchor if c["trimp"] is not None else None
    return canon, anchor


def compute_pmc(canon, start_date, end_date):
    daily_belastung = defaultdict(float)
    for c in canon:
        if c["belastung"] is not None:
            daily_belastung[c["date"]] += c["belastung"]

    days = []
    d = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    while d <= end:
        days.append(d.isoformat())
        d += datetime.timedelta(days=1)

    load = [daily_belastung.get(dt, 0.0) for dt in days]
    fitness, fatigue, fresh = [0.0] * len(days), [0.0] * len(days), [0.0] * len(days)
    for i in range(len(days)):
        if i == 0:
            fitness[i] = load[i] / 42
            fatigue[i] = load[i] / 7
        else:
            fitness[i] = fitness[i - 1] + (load[i] - fitness[i - 1]) / 42
            fatigue[i] = fatigue[i - 1] + (load[i] - fatigue[i - 1]) / 7
        fresh[i] = fitness[i] - fatigue[i]

    activity_dates = set(c["date"] for c in canon)
    no_record_days = [dt for dt in days if dt not in activity_dates]
    return dict(days=days, load=load, fitness=fitness, fatigue=fatigue, fresh=fresh,
                no_record_days=no_record_days)


def main():
    state_path = os.path.join(CACHE, "state.json")
    state = load_cache("state.json", {"last_synced_date": None})

    ah = load_cache("apple_health_workouts.json", [])
    garmin = load_cache("garmin_activities.json", [])
    garmin_period_start = state.get("garmin_period_start", "2026-06-22")

    canon = build_canonical_activities(ah, garmin, garmin_period_start)
    canon = compute_trimp(canon)
    canon, anchor = compute_belastung(canon)

    if not canon:
        print("Kein Cache gefunden -- siehe README.md, Schritt 1-2, fuer den Erstlauf.")
        return

    start_date = min(c["date"] for c in canon)
    end_date = datetime.date.today().isoformat()
    pmc = compute_pmc(canon, start_date, end_date)

    print(f"{len(canon)} Einheiten, Anker={anchor:.1f}, "
          f"Fitness heute={pmc['fitness'][-1]:.1f}, Frische heute={pmc['fresh'][-1]:.1f}")

    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "canon_activities.json"), "w", encoding="utf-8") as f:
        json.dump(canon, f, ensure_ascii=False)
    with open(os.path.join(CACHE, "pmc_series.json"), "w", encoding="utf-8") as f:
        json.dump(pmc, f, ensure_ascii=False)

    state["last_synced_date"] = end_date
    state["garmin_period_start"] = garmin_period_start
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

    print("Zwischenstand geschrieben. Fuer die vollstaendige page_data.json (Zonen, Bestleistungen,")
    print("Coach-Analyse, Wochen-Bubbles) noch die Aggregationsschritte aus dem urspruenglichen")
    print("Chat-Durchlauf ausfuehren -- die sind bewusst nicht 1:1 hier eingebaut, weil Zonen,")
    print("Bestleistungen und der Coach-Befund menschliche Lektuere der Rohdaten brauchen,")
    print("kein stures Neu-Rechnen. Ein frischer Claude-Lauf soll page_data.json aus diesen")
    print("Zwischendateien plus den neuen Rohantworten bauen, dann page_template.html fuellen.")


if __name__ == "__main__":
    main()
