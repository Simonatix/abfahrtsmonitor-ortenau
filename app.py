import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
EFA_BASE = os.environ.get("EFA_BW_BASE", "https://www.efa-bw.de/rtMonitor").rstrip("/")
MOCK_DIR = os.environ.get("EFA_MOCK_DIR") or None
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
ORTENAU_PREFIX = "de:08317:"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

MOT_LABEL = {
    "0": "Zug", "1": "S-Bahn", "2": "U-Bahn", "3": "Stadtbahn", "4": "Tram",
    "5": "Stadtbus", "6": "Regionalbus", "7": "Schnellbus", "8": "Seilbahn",
    "9": "Schiff", "10": "AST", "11": "Sonstige", "12": "Flugzeug",
    "13": "Zug", "14": "Zug", "15": "Zug", "16": "Zug", "17": "SEV", "18": "Zug",
    "19": "Bürgerbus", "20": "Rufbus", "21": "Fernbus",
}
MOT_KIND = {
    "0": "bahn", "1": "bahn", "8": "bahn",
    "13": "bahn", "14": "bahn", "15": "bahn", "16": "bahn", "17": "bahn", "18": "bahn",
    "5": "bus", "6": "bus", "7": "bus", "19": "bus", "20": "bus", "21": "bus",
}


class EfaError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def efa_get(endpoint, params):
    if MOCK_DIR:
        key = params.get("name_sf") or params.get("name_dm") or ""
        path = Path(MOCK_DIR) / f"{endpoint}__{_slug(key)}.json"
        if not path.is_file():
            raise EfaError(404, f"Keine Mock-Daten für „{key}“ ({path.name})")
        return json.loads(path.read_text(encoding="utf-8"))
    query = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())
    request = urllib.request.Request(
        f"{EFA_BASE}/{endpoint}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise EfaError(exc.code, f"EFA-BW antwortet mit HTTP {exc.code}") from exc
    except Exception as exc:
        raise EfaError(502, f"EFA-BW nicht erreichbar ({exc})") from exc


def _points(container):
    points = (container or {}).get("points")
    if isinstance(points, list):
        return points
    if isinstance(points, dict):
        return _as_list(points.get("point"))
    return []


def _is_stop(point):
    return point.get("type") == "stop" or point.get("anyType") == "stop"


def search_stops(query, local_only=True):
    data = efa_get("XML_STOPFINDER_REQUEST", {
        "language": "de",
        "outputFormat": "JSON",
        "stateless": "1",
        "locationServerActive": "1",
        "type_sf": "any",
        "name_sf": query,
    })
    stops = []
    for point in _points(data.get("stopFinder")):
        if not _is_stop(point):
            continue
        ref = point.get("ref") or {}
        stops.append({
            "id": ref.get("id", ""),
            "gid": ref.get("gid", ""),
            "name": point.get("name", ""),
            "place": ref.get("place", ""),
            "modes": point.get("modes", ""),
        })
    if local_only:
        local = [s for s in stops if s["gid"].startswith(ORTENAU_PREFIX)]
        if local:
            stops = local
    return stops[:12]


def _hhmm(dt):
    return f"{int(dt.get('hour', 0)):02d}:{int(dt.get('minute', 0)):02d}"


def _server_time(data):
    for param in _as_list(data.get("parameters")):
        if param.get("name") == "serverTime":
            return param.get("value", "")
    return ""


def get_departures(gid, limit=40):
    data = efa_get("XML_DM_REQUEST", {
        "language": "de",
        "outputFormat": "JSON",
        "stateless": "1",
        "locationServerActive": "1",
        "mode": "direct",
        "type_dm": "any",
        "name_dm": gid,
        "useRealtime": "1",
        "itdTripDateTimeDepArr": "dep",
        "mergeDep": "1",
    })
    dm_points = _points(data.get("dm"))
    stop_name = dm_points[0].get("name", "") if dm_points else ""
    departures = []
    for dep in _as_list(data.get("departureList")):
        line_info = dep.get("servingLine") or {}
        planned_dt = dep.get("dateTime") or {}
        real_dt = dep.get("realDateTime")
        raw_delay = line_info.get("delay")
        delay = None
        try:
            parsed = int(raw_delay)
            if parsed > -9999:
                delay = parsed
        except (TypeError, ValueError):
            pass
        cancelled = dep.get("realtimeStatus") == "DEPARTURE_CANCELLED" or raw_delay == "-9999"
        mot = str(line_info.get("motType", ""))
        line = (line_info.get("number") or "").strip()
        if line_info.get("trainType") and line_info.get("trainNum"):
            line = f"{line_info['trainType']} {line_info['trainNum']}"
        elif line_info.get("trainName") and line_info["trainName"] in line:
            line = line.replace(line_info["trainName"], "").strip()
        planned = _hhmm(planned_dt)
        planned_date = (
            f"{planned_dt.get('year', '')}-"
            f"{int(planned_dt.get('month', 0) or 0):02d}-"
            f"{int(planned_dt.get('day', 0) or 0):02d}"
        )
        real = _hhmm(real_dt) if real_dt else planned
        try:
            countdown = int(dep.get("countdown"))
        except (TypeError, ValueError):
            countdown = None
        departures.append({
            "line": line,
            "label": MOT_LABEL.get(mot, line_info.get("name", "") or "ÖPNV"),
            "kind": MOT_KIND.get(mot, "other"),
            "product": line_info.get("name", ""),
            "direction": line_info.get("direction", ""),
            "planned": planned,
            "plannedDate": planned_date,
            "real": real,
            "delay": delay,
            "countdown": countdown,
            "platform": dep.get("platformName") or dep.get("platform") or "",
            "stopName": dep.get("stopName", ""),
            "cancelled": cancelled,
            "status": dep.get("realtimeStatus", ""),
            "realtime": line_info.get("realtime") == "1",
            "hints": [h.get("content", "") for h in _as_list(line_info.get("hints")) if h.get("content")],
        })
    departures.sort(key=lambda d: (d["plannedDate"], d["real"]))
    return {
        "stop": {"name": stop_name, "gid": gid},
        "serverTime": _server_time(data),
        "departures": departures[:limit],
    }


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "OrtenauMonitor/1.0"

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, message):
        self._send_json({"error": message}, status)

    def _send_file(self, path):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                self._send_file(STATIC_DIR / "index.html")
            elif path.startswith("/static/"):
                target = (STATIC_DIR / path[len("/static/"):]).resolve()
                if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
                    return self._send_error_json(404, "Datei nicht gefunden")
                self._send_file(target)
            elif path == "/api/stops":
                query = (params.get("q") or [""])[0].strip()
                if len(query) < 2:
                    return self._send_error_json(400, "Suchbegriff zu kurz (min. 2 Zeichen)")
                self._send_json({"query": query, "stops": search_stops(query)})
            elif path == "/api/departures":
                gid = (params.get("stop") or [""])[0].strip()
                if not gid:
                    return self._send_error_json(400, "Parameter „stop“ fehlt")
                self._send_json(get_departures(gid))
            else:
                self._send_error_json(404, "nicht gefunden")
        except EfaError as exc:
            self._send_error_json(exc.status, exc.message)
        except Exception as exc:
            self._send_error_json(500, f"Interner Fehler: {exc}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    host, port = server.server_address[:2]
    print(f"Abfahrtsmonitor Ortenaukreis läuft auf http://{host}:{port}")
    print(f"Datenquelle: EFA-BW ({EFA_BASE})" + (" [Mock-Modus]" if MOCK_DIR else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
