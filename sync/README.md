# Trainingsanalyse — Sync & Build

Baut `trainingsanalyse.html` aus rohen Garmin-Daten neu. Kein Abo, keine
fremde Analyse-Schicht — die Formeln stehen unten und im Code.

## Einmalige Einrichtung (bei dir lokal, nicht in einer Claude-Sitzung)

```
cd HWPO-coach
python3 -m venv sync/.venv
sync/.venv/bin/pip install --upgrade pip garminconnect
sync/.venv/bin/python sync/garmin_login.py
```

`garmin_login.py` fragt Mailadresse und Passwort ab (Passwort per `getpass`,
wird nirgends gespeichert oder geloggt), meldet dich bei Garmin Connect an
und legt einen Sitzungs-Token unter `sync/.garmin_tokens/` ab (git-ignoriert).
Braucht ein echtes Terminal — läuft nicht headless, nicht aus einer
Claude-Sitzung heraus.

Danach reicht für jeden weiteren Sync:

```
sync/.venv/bin/python sync/garmin_sync.py
```

ohne erneutes Passwort, bis Garmin die Sitzung irgendwann invalidiert — dann
`garmin_login.py` einmal erneut ausführen.

### Warum nicht Athletedata

Der erste Aufbau dieser Seite lief über den Athletedata-MCP-Zugang (bequemer,
aber nur innerhalb einer Claude-Sitzung erreichbar — eine echte, unbeaufsichtigte
Automatisierung per cron/LaunchAgent kam da nicht dran). `garmin_sync.py`
spricht jetzt direkt mit `garminconnect` (Python-Paket, Stand 0.3.2 — Methodennamen
unten gegen die installierte Fassung geprüft, nicht blind aus einer Doku
übernommen), läuft also komplett lokal, ohne Claude.

**Ungeprüfter Punkt, ehrlich benannt:** Ich habe `garmin_sync.py` ohne Zugriff
auf ein echtes Garmin-Konto geschrieben (kein Login aus dieser Sitzung möglich).
Die Feldnamen der Aktivitäts-Antwort (Distanz, Dauer, Puls) sind mehrfach
kandidiert, aber nicht verifiziert. Lauf beim ersten Mal:

```
sync/.venv/bin/python sync/garmin_sync.py --debug-first
```

Das druckt den kompletten Rohblock der ersten neuen Aktivität und speichert
nichts. Prüf, ob `DISTANCE_KEYS`/`DURATION_KEYS`/`AVG_HR_KEYS`/`MAX_HR_KEYS`
in `garmin_sync.py` die richtigen Felder treffen, bevor du ohne `--debug-first`
laufen lässt.

## Wiederkehrend einrichten (macOS LaunchAgent)

Ruf die venv-Python direkt auf, keine Shell dazwischen (sonst fehlen im
Dokumentenordner die Rechte):

```xml
<!-- ~/Library/LaunchAgents/com.hwpo.trainingsync.plist -->
<key>ProgramArguments</key>
<array>
  <string>/absoluter/pfad/zu/HWPO-coach/sync/.venv/bin/python</string>
  <string>/absoluter/pfad/zu/HWPO-coach/sync/garmin_sync.py</string>
</array>
<key>StartCalendarInterval</key>
<dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
```

Linux: `crontab -e` → `0 7 * * 1 /pfad/HWPO-coach/sync/.venv/bin/python /pfad/HWPO-coach/sync/garmin_sync.py`
Windows: Aufgabenplanung, Aktion = derselbe venv-`python.exe`-Pfad + Skriptpfad als Argument.

Die Seite aktualisiert sich nicht von selbst — sie wird neu gerechnet, wenn
dieser Befehl läuft. Läuft er montags, ist die Seite montags aktuell.

## Ablauf, den `garmin_sync.py` bei jedem Lauf durchgeht

1. Sitzungs-Token aus `sync/.garmin_tokens/` laden (kein Passwort nötig).
2. `sync/cache/state.json` lesen für `last_synced_date`.
3. `get_activities_by_date(last_synced_date, heute)` — nur die neuen.
4. Je neuer Aktivität: `get_activity_splits(id)` für Runden-Auflösung der
   TRIMP-Rechnung (Rückfall auf Aktivitäts-Durchschnitt, wenn das fehlschlägt).
5. TRIMP/Belastung/Fitness-Fatigue-Freshness auf dem Gesamtbestand neu rechnen
   (`build_analysis.py`, die 42/7-Tage-Glättung braucht die volle Reihe, nicht
   nur die neuen Tage).
6. Zwischenstand in `sync/cache/` schreiben, `state.json` aktualisieren.
7. Committen und pushen (Zonen, Bestleistungen, Wochen-Bubbles und der
   Coach-Befund in `page_data.json`/`trainingsanalyse.html` bleiben dabei
   unverändert — die brauchen prüfende Lektüre der Rohdaten, kein stures
   Neu-Rechnen; dafür eine Claude-Sitzung mit Zugriff auf das Repo bitten).

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

## Bekannte, offen ausgewiesene Vereinfachungen (Stand Erstaufbau, 13.09.2026)

- Beim Erstaufbau hatten nur **20 von 249** Einheiten eine Runden-/Split-Auflösung
  für die TRIMP-Rechnung; der Rest lief auf Basis des Aktivitäts-Durchschnittspulses.
- `RHR` (46 bpm) und `HRMAX` (197 bpm) sind als Konstanten in
  `build_analysis.py` hinterlegt (10.-Perzentil-Baseline bzw. gemessenes,
  ≥60s gehaltenes Maximum aus dem Erstaufbau). Bei einem neuen, höheren
  Maximalpuls-Fund: Wert ersetzen und dazuschreiben, woher er kommt.
- Geschlechts-Annahme für die TRIMP-Konstanten (0,64/1,92 statt 0,86/1,67):
  aus dem Vornamen abgeleitet, nicht bestätigt.
- Bestleistungen kommen aus 1-km-Splits (Näherung), nicht aus einer echten
  Sekundenreihe.
- Ab dem Umstieg auf `garminconnect` (13.09.2026) ist die im Erstaufbau
  verwendete Apple-Health-Vorgeschichte (13.09.2025–16.08.2026) eingefroren;
  neue Einheiten kommen nur noch direkt von Garmin. Das ist in Ordnung, weil
  seit dem 17.08.2026 ohnehin ausschließlich mit Garmin-Gerät aufgezeichnet
  wird.

## Dateien

- `garmin_login.py` — einmaliger interaktiver Login, legt den Sitzungs-Token an
- `garmin_sync.py` — headless, wiederkehrend: neue Aktivitäten holen, TRIMP/PMC
  neu rechnen, committen/pushen
- `build_analysis.py` — die TRIMP-/Belastungs-/Fitness-Formeln als Code,
  von beiden obigen Skripten importiert
- `page_template.html` — das Seiten-Grundgerüst mit `__DATA__`-Platzhalter
- `cache/`, `.garmin_tokens/`, `.venv/` — alle git-ignoriert (Gesundheitsdaten,
  Sitzungs-Token, virtuelle Umgebung)
