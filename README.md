# Abfahrtsmonitor Ortenaukreis

Minimale Web-App, die Bus- und Zugverbindungen im **Ortenaukreis (Baden-Württemberg)** abgreift
und die **Ankunfts-/Abfahrtszeiten an einer Haltestelle** anzeigt – inklusive Echtzeit-Prognose
(Verspätung, Ausfälle, Gleis/Steig).

## Datenquelle

- **EFA-BW** – das landesweite Fahrplanauskunftssystem der NVBW (Nahverkehrsgesellschaft
  Baden-Württemberg), das auch bwegt.de und den Verkehrsverbund Ortenau (VGO) versorgt.
  - Haltestellensuche: `XML_STOPFINDER_REQUEST` (JSON)
  - Abfahrtsmonitor: `XML_DM_REQUEST` mit `useRealtime=1` (JSON)
  - Basis-URL: `https://www.efa-bw.de/rtMonitor` ( von MobiData BW öffentlich dokumentierter
    Monitor-Endpunkt; alternatives Layout z. B. `/nvbw3L`, siehe `EFA_BW_BASE`)
- Haltestellen werden eindeutig über die **DHID** angesprochen, z. B. `de:08317:14506`
  (Offenburg Hbf). Das Präfix `de:08317:` = Ortenaukreis; die Suche ist darauf eingeschränkt.
- Lizenz der Daten: **Datenlizenz Deutschland – Namensnennung 2.0** (NVBW).
- Hinweis: Die EFA-XML-Schnittstelle wird laut MobiData BW **Ende 2027 eingestellt**; die
  Nachfolgeschnittstelle ist die TRIAS-API (VDV 431-2, Zugang nach Registrierung bei der NVBW).

## Starten

Voraussetzung: Python 3.10+ (nur Standardbibliothek, keine Abhängigkeiten).

```bash
python3 app.py
# dann öffnen: http://127.0.0.1:8000
```

Der Server lauscht nur auf `127.0.0.1` (Loopback) und proxied die EFA-BW-Anfragen serverseitig
(keine CORS-Probleme im Browser).

### Umgebungsvariablen

| Variable | Standard | Bedeutung |
|---|---|---|
| `PORT` | `8000` | Port des Webservers |
| `HOST` | `127.0.0.1` | Bind-Adresse (nur Loopback lassen!) |
| `EFA_BW_BASE` | `https://www.efa-bw.de/rtMonitor` | EFA-BW-Instanz |
| `EFA_MOCK_DIR` | – | Wenn gesetzt: Antworten aus JSON-Dateien statt Live-Abfrage (z. B. `fixtures/` für Demo/Tests ohne Netz) |

Beispiel Offline-Demo mit aufgezeichneten Live-Daten:

```bash
EFA_MOCK_DIR=fixtures python3 app.py
```

## Bedienung

1. Haltestelle ins Suchfeld eingeben (z. B. „Offenburg Hbf“, „Achern“, „Kehl Rathaus“) oder
   Schnellwahl-Button klicken.
2. Haltestelle aus der Vorschlagliste wählen.
3. Abfahrtstafel mit Soll-/Prognosezeit, Verspätung, Gleis/Steig und Status; Filter
   „Alle / Bus / Bahn"; automatische Aktualisierung alle 30 s.

## API

| Endpunkt | Beschreibung |
|---|---|
| `GET /api/stops?q=<text>` | Haltestellensuche im Ortenaukreis → `{stops: [{id, gid, name, place, modes}]}` |
| `GET /api/departures?stop=<DHID>` | Nächste Abfahrten → `{stop, serverTime, departures: [{line, kind, direction, planned, real, delay, countdown, platform, cancelled, …}]}` |

`kind` ist `bus`, `bahn` oder `other`; `cancelled: true` bei Ausfällen; `delay` in Minuten
(`null` = keine Echtzeit-Prognose).

## Tests

```bash
python3 test_app.py
```

Die Tests laufen offline gegen die aufgezeichneten EFA-Antworten in `fixtures/`
(6 Haltestellen im Ortenaukreis: Achern Bf, Offenburg Hbf, Kehl Rathaus, Lahr/Kuhbach Rathaus,
Gengenbach Bf, Legelshurst Bf – jeweils Suche + Abfahrtsmonitor).

## Projektstruktur

```
app.py                  Server (http.server), EFA-BW-Client, JSON-API, Static-Files
static/index.html       Oberfläche
static/app.js           Suche, Vorschlagliste, Abfahrtstafel, Auto-Refresh
static/style.css        Styling
test_app.py             Unit- + API-Tests (Mock-Modus)
fixtures/               aufgezeichnete EFA-BW-JSON-Antworten (Tests / Offline-Demo)
```
