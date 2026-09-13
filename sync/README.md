# Trainingsanalyse — Sync & Build

Baut `trainingsanalyse.html` aus rohen Garmin- und Apple-Health-Daten neu. Kein Abo,
keine fremde Analyse-Schicht — die Formeln stehen unten und im Code.

## Warum das kein normales Cron-Skript ist

Die Rohdaten kommen über den **Athletedata-MCP-Zugang**, der nur innerhalb einer
Claude-Sitzung erreichbar ist (Garmin- und Apple-Health-Werkzeuge, siehe unten).
Es gibt kein portables API-Token, das ein eigenständiges Python-Skript außerhalb
von Claude verwenden könnte. Die "Automatisierung" ist deshalb eine wöchentliche
**Routine**, die eine neue Claude-Sitzung anstößt; diese Sitzung ruft die
Athletedata-Werkzeuge auf, cached die Rohantworten unter `sync/cache/` und führt
danach `python3 sync/build_analysis.py` aus, um `trainingsanalyse.html` neu zu
schreiben.

## Ablauf, den eine Sitzung bei jedem Lauf durchgeht

1. **Letzten Stand finden**: `sync/cache/state.json` liest `last_synced_date`.
   Fehlt die Datei, ist es ein Erstlauf (siehe Schritt 1–2 im ursprünglichen
   Chat-Verlauf für die volle 12-Monats-Historie).
2. **Neue Aktivitäten holen** (nur seit `last_synced_date`, nicht neu von vorn):
   - `garmin_get_activities(start_date, end_date=heute)` — Übersicht
   - `apple_health_get_workouts(start_date, end_date=heute)` — falls Garmin für
     den Zeitraum Lücken hat (Coverage-Gap-Hinweis der Tools beachten)
   - Für neue Garmin-Aktivitäten mit eigenem Gerät (deviceName gesetzt):
     `get_activity_detail(source_activity_id=...)` für Runden/Splits, wo eine
     Einheit als "letzter Lauf" auf der Seite erscheinen soll
3. **Deduplizieren**: Cycling/Rowing/Strength-Einträge, die sowohl bei Garmin
   (geräte-los, aus einem Smart-Trainer/Ruder-Ergometer) als auch bei Apple
   Health auftauchen, per Datum+Dauer (±5s) matchen — Garmin-Version behalten
   (hat Watt/Trainingslast). Alles ab dem Datum, an dem `deviceName` in
   `garmin_get_activities` zuverlässig gesetzt ist, zählt als Garmin-Periode;
   Apple Health wird für diesen Zeitraum komplett ignoriert (sonst Doppelzählung
   — geprüft: Garmin synct auch zu Apple Health zurück).
4. **Cache aktualisieren**: neue Rohantworten an `sync/cache/*.json` anhängen,
   `state.json.last_synced_date` auf heute setzen.
5. **Build**: `python3 sync/build_analysis.py` liest den kompletten Cache, rechnet
   alles neu (nicht nur die neuen Tage — die 42/7-Tage-Glättung braucht die volle
   Reihe) und schreibt `../trainingsanalyse.html`.
6. **Commit & Push** auf den aktuellen Branch, kurze Notiz an den Nutzer.

## Formeln (siehe auch build_analysis.py, dort maßgeblich)

```
TRIMP:  hr_i = (HF_i − RUHEPULS) / (MAXPULS − RUHEPULS), auf [0,1] gedeckelt
        w_i  = hr_i · 0,64 · e^(1,92·hr_i)     [männlich — siehe ATHLETE_GENDER]
        TRIMP_Einheit = Σ w_i · dauer_segment_s / 60   (Runden-/Split-Segmente,
                        oder ein Segment = ganze Dauer, wenn keine Runden vorliegen)

Anker:  95. Perzentil der Tages-TRIMP-Summen (aktive Tage), mind. 40
Belastung = 100 × TRIMP_Einheit / Anker      -- NICHT gedeckelt bei 100

Fitness(t)   = Fitness(t-1)   + (Tages-Belastung(t) − Fitness(t-1))   / 42
Ermüdung(t)  = Ermüdung(t-1)  + (Tages-Belastung(t) − Ermüdung(t-1))  / 7
Frische(t)   = Fitness(t-1) − Ermüdung(t-1)
```

## Bekannte, offen ausgewiesene Vereinfachungen (Stand erster Lauf, 13.09.2026)

- Nur **20 von 249** Einheiten hatten eine Runden-/Split-Auflösung für die
  TRIMP-Rechnung; der Rest lief auf Basis des Aktivitäts-Durchschnittspulses.
  Bei künftigen Läufen: wenn `get_activity_detail` Splits/Laps liefert, IMMER
  verwenden statt des nackten Durchschnitts.
- `RHR` (46 bpm) und `HRMAX` (197 bpm) sind als Konstanten in
  `build_analysis.py` hinterlegt (10.-Perzentil-Baseline bzw. gemessenes,
  ≥60s gehaltenes Maximum). Bei einem neuen, höheren Maximalpuls-Fund: Wert
  ersetzen und dazuschreiben, woher er kommt.
- Geschlechts-Annahme für die TRIMP-Konstanten (0,64/1,92 statt 0,86/1,67):
  aus dem Vornamen abgeleitet, nicht bestätigt.
- Bestleistungen kommen aus 1-km-Splits (Näherung), nicht aus einer echten
  Sekundenreihe.

## Dateien

- `build_analysis.py` — die ganze Rechnung, von Rohdaten-Cache bis `page_data.json`
- `page_template.html` — das Seiten-Grundgerüst mit `__DATA__`-Platzhalter
- `cache/` — Rohantworten der Athletedata-Werkzeuge (gitignored, enthält
  Gesundheitsdaten)
