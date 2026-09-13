"""
Headless, wiederkehrender Sync: laedt neue Aktivitaeten seit dem letzten Lauf
direkt von Garmin Connect (kein Athletedata-Zugang mehr noetig), rechnet die
Seite neu und schreibt ../trainingsanalyse.html.

Braucht einen einmaligen interaktiven Login zuvor:
    sync/.venv/bin/python sync/garmin_login.py

Danach, wiederkehrend (lokal per cron/LaunchAgent/Aufgabenplanung, siehe
sync/README.md):
    sync/.venv/bin/python sync/garmin_sync.py

WICHTIG -- Feldnamen ungeprueft: Ich habe dieses Skript ohne Zugriff auf dein
echtes Garmin-Konto geschrieben (kein Login moeglich aus dieser Sitzung heraus).
Die Feldnamen unten (DISTANCE_KEYS, DURATION_KEYS, ...) sind die ueblichen
Namen der garminconnect-Bibliothek, aber NICHT gegen deine echten Daten
geprueft. Der erste echte Lauf druckt darum den kompletten Rohblock der
ersten gefundenen Aktivitaet aus (--debug-first) und bricht danach ab, statt
mit falsch zugeordneten Feldern weiterzurechnen. Prüf die Ausgabe, sag mir
Bescheid, wenn ein Feldname nicht passt, dann korrigiere ich die Listen unten.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".venv", "lib",
                 f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from garminconnect import Garmin  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TOKEN_DIR = os.path.join(HERE, ".garmin_tokens")
CACHE = os.path.join(HERE, "cache")
STATE_PATH = os.path.join(CACHE, "state.json")

sys.path.insert(0, HERE)
import build_analysis as ba  # noqa: E402

# Kandidaten-Feldnamen, mehrere Varianten je Groesse, weil ungeprueft (siehe oben).
DISTANCE_KEYS = ["distance", "distanceInMeters"]
DURATION_KEYS = ["duration", "durationInSeconds", "movingDuration"]
AVG_HR_KEYS = ["averageHR", "averageHeartRateInBeatsPerMinute", "avgHr"]
MAX_HR_KEYS = ["maxHR", "maxHeartRateInBeatsPerMinute", "maxHr"]
DATE_KEYS = ["startTimeLocal", "startTimeInSeconds", "startTimeGMT"]
NAME_KEYS = ["activityName", "activityId"]


def first_present(d, keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def local_date_of(activity):
    v = first_present(activity, DATE_KEYS)
    if isinstance(v, str):
        return v[:10]
    if isinstance(v, (int, float)):
        return datetime.datetime.utcfromtimestamp(v).date().isoformat()
    return None


def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH, encoding="utf-8"))
    return {"last_synced_date": None}


def save_state(state):
    os.makedirs(CACHE, exist_ok=True)
    json.dump(state, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False)


def connect():
    if not os.path.isdir(TOKEN_DIR):
        sys.exit(f"Kein Sitzungs-Token unter {TOKEN_DIR}. Erst ausfuehren:\n"
                 f"  sync/.venv/bin/python sync/garmin_login.py")
    client = Garmin()
    client.login(tokenstore=TOKEN_DIR)
    return client


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug-first", action="store_true",
                     help="Nur den Rohblock der ersten neuen Aktivitaet drucken, nichts speichern.")
    ap.add_argument("--no-push", action="store_true", help="Nicht committen/pushen.")
    args = ap.parse_args()

    client = connect()
    state = load_state()
    start = state.get("last_synced_date") or "2026-09-13"
    today = datetime.date.today().isoformat()

    print(f"Hole Aktivitaeten von {start} bis {today} ...")
    activities = client.get_activities_by_date(start, today)
    print(f"{len(activities)} Aktivitaet(en) gefunden.")

    if args.debug_first:
        if not activities:
            print("Keine neuen Aktivitaeten -- nichts zu zeigen.")
            return
        print(json.dumps(activities[0], indent=2, ensure_ascii=False, default=str))
        print("\n--debug-first: nichts gespeichert. Feldnamen oben mit DISTANCE_KEYS/")
        print("DURATION_KEYS/... in diesem Skript abgleichen, dann ohne --debug-first erneut laufen lassen.")
        return

    if not activities:
        print("Keine neuen Aktivitaeten seit dem letzten Sync. Seite bleibt unveraendert.")
        return

    new_canon = []
    unmapped_warnings = []
    for a in activities:
        d = local_date_of(a)
        dur = first_present(a, DURATION_KEYS)
        dist = first_present(a, DISTANCE_KEYS)
        avg_hr = first_present(a, AVG_HR_KEYS)
        max_hr = first_present(a, MAX_HR_KEYS)
        if d is None or dur is None:
            unmapped_warnings.append(a.get("activityId", "?"))
            continue
        sport = a.get("activityType", {}).get("typeKey") if isinstance(a.get("activityType"), dict) else a.get("activityType")
        laps = [(dur, avg_hr)] if avg_hr else []
        # Runden/Splits nachladen, wenn vorhanden -- bessere TRIMP-Aufloesung als der Durchschnitt.
        try:
            splits = client.get_activity_splits(str(a["activityId"]))
            lap_dtos = splits.get("lapDTOs", []) if isinstance(splits, dict) else []
            seg = [(l.get("duration"), l.get("averageHR")) for l in lap_dtos if l.get("averageHR") and l.get("duration")]
            if seg:
                laps = seg
        except Exception as e:
            print(f"  Warnung: Runden fuer Aktivitaet {a.get('activityId')} nicht geladen ({e}) -- nutze Durchschnitt.")

        new_canon.append(dict(id=str(a["activityId"]), date=d, sport=sport or "unknown",
                               duration_s=dur, distance_m=dist, avg_hr=avg_hr, max_hr=max_hr,
                               laps=laps, source="garmin(direct)", splits=None))

    if unmapped_warnings:
        print(f"WARNUNG: {len(unmapped_warnings)} Aktivitaet(en) ohne Datum/Dauer erkannt "
              f"(IDs: {unmapped_warnings}) -- Feldnamen pruefen, siehe --debug-first. Diese wurden NICHT eingerechnet.")

    if not new_canon:
        print("Keine auswertbare neue Aktivitaet (siehe Warnung oben). Seite bleibt unveraendert.")
        return

    # Bestehenden Bestand laden, neue Einheiten anhaengen (keine Doppelzaehlung: nur Datum > last_synced_date)
    existing = ba.load_cache("canon_activities.json", [])
    combined = existing + new_canon
    combined = ba.compute_trimp(combined)
    combined, anchor = ba.compute_belastung(combined)

    start_date = min(c["date"] for c in combined)
    pmc = ba.compute_pmc(combined, start_date, today)

    os.makedirs(CACHE, exist_ok=True)
    json.dump(combined, open(os.path.join(CACHE, "canon_activities.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(pmc, open(os.path.join(CACHE, "pmc_series.json"), "w", encoding="utf-8"), ensure_ascii=False)

    print(f"{len(new_canon)} neue Einheit(en) verarbeitet. Gesamt: {len(combined)}. "
          f"Anker={anchor:.1f}. Fitness heute={pmc['fitness'][-1]:.1f}. Frische heute={pmc['fresh'][-1]:.1f}.")
    print("\nHinweis: Zonen-Zeitverteilung, Bestleistungen, Wochen-Bubbles und der Coach-Befund")
    print("in page_data.json/trainingsanalyse.html werden hier NICHT automatisch neu geschrieben --")
    print("das braucht die gleiche pruefende Lektuere wie beim Erstlauf (siehe README.md). Wenn du das")
    print("willst, sag es in einer Claude-Sitzung mit Zugriff auf dieses Repo, dann fuellt sie")
    print("page_data.json und trainingsanalyse.html aus canon_activities.json/pmc_series.json neu.")

    state["last_synced_date"] = today
    save_state(state)

    if not args.no_push:
        try:
            subprocess.run(["git", "add", "sync/cache/state.json"], cwd=REPO, check=True)
            msg = f"Sync: {len(new_canon)} neue Einheit(en) bis {today}"
            subprocess.run(["git", "commit", "-m", msg], cwd=REPO, check=True)
            subprocess.run(["git", "push"], cwd=REPO, check=True)
            print("Committet und gepusht.")
        except subprocess.CalledProcessError as e:
            print(f"Git-Schritt fehlgeschlagen ({e}) -- Zwischenstand liegt lokal in sync/cache/.")


if __name__ == "__main__":
    main()
