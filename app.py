import argparse
import json
import sqlite3
import sys
import threading
import time
import webbrowser
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "datos" / "desahogos.sqlite3"
HOUR = 3600
MAX_MESSAGE_LENGTH = 2000


@contextmanager
def connect(database):
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            yield connection


def initialize(database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with connect(database) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS venting (
                id INTEGER PRIMARY KEY,
                application_id INTEGER NOT NULL REFERENCES applications(id),
                message TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS venting_application_date
                ON venting(application_id, created_at, id);
        """)
        connection.execute("INSERT OR IGNORE INTO applications (name) VALUES (?)", ("aXet.code",))


def calculate_activity(timestamps, now):
    active = 0
    next_decay = None
    for timestamp in timestamps:
        if timestamp > now:
            break
        if next_decay is not None and timestamp >= next_decay:
            elapsed = int((timestamp - next_decay) // HOUR) + 1
            active = max(0, active - elapsed)
            next_decay = next_decay + elapsed * HOUR if active else None
        if active == 0:
            next_decay = timestamp + HOUR
        active += 1
    if next_decay is not None and now >= next_decay:
        elapsed = int((now - next_decay) // HOUR) + 1
        active = max(0, active - elapsed)
        next_decay = next_decay + elapsed * HOUR if active else None
    return active, next_decay


def state_for(active):
    if active == 0:
        return "calm"
    if active <= 2:
        return "uneasy"
    if active <= 5:
        return "hot"
    return "fire"


def iso_time(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def snapshot(database, now=None):
    now = time.time() if now is None else now
    with connect(database) as connection:
        applications = connection.execute("SELECT id, name FROM applications ORDER BY name").fetchall()
        result = []
        for application in applications:
            rows = connection.execute(
                "SELECT id, message, created_at FROM venting WHERE application_id = ? ORDER BY created_at DESC, id DESC",
                (application["id"],),
            ).fetchall()
            active, next_decay = calculate_activity((row["created_at"] for row in reversed(rows)), now)
            result.append({
                "id": application["id"],
                "name": application["name"],
                "active": active,
                "state": state_for(active),
                "next_decay": iso_time(next_decay) if next_decay is not None else None,
                "history": [{"id": row["id"], "message": row["message"], "created_at": iso_time(row["created_at"])} for row in rows],
            })
        return {"applications": result, "server_time": iso_time(now)}


def make_handler(database):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def send_json(self, status, data):
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            host = self.headers.get("Host", "").lower()
            port = self.server.server_port
            return host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.valid_host():
                self.send_error(400)
                return
            path = urlsplit(self.path).path
            if path == "/api/state":
                self.send_json(200, snapshot(database))
                return
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/iconosAplicaciones/axet.png": ("iconosAplicaciones/axet.png", "image/png")}
            if path not in files:
                self.send_error(404)
                return
            filename, content_type = files[path]
            try:
                payload = (ROOT / filename).read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            if not self.valid_host():
                self.send_error(400)
                return
            if urlsplit(self.path).path != "/api/venting":
                self.send_error(404)
                return
            origin = self.headers.get("Origin", "")
            if origin != f"http://{self.headers.get('Host', '')}":
                self.send_json(403, {"error": "Origen no permitido."})
                return
            if self.headers.get_content_type() != "application/json":
                self.send_json(415, {"error": "Formato no válido."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16384:
                    raise ValueError
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                application_id = data["application_id"]
                message = data["message"]
                if type(application_id) is not int or not isinstance(message, str):
                    raise ValueError
                message = message.strip()
                if not message or len(message) > MAX_MESSAGE_LENGTH:
                    raise ValueError
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                self.send_json(400, {"error": f"Escribe un mensaje de entre 1 y {MAX_MESSAGE_LENGTH} caracteres."})
                return
            with connect(database) as connection:
                if not connection.execute("SELECT 1 FROM applications WHERE id = ?", (application_id,)).fetchone():
                    self.send_json(404, {"error": "No se encontró el aplicativo."})
                    return
                connection.execute("INSERT INTO venting (application_id, message, created_at) VALUES (?, ?, ?)", (application_id, message, time.time()))
            self.send_json(201, snapshot(database))

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Botón de desahogo: aplicación local")
    parser.add_argument("--port", type=int, default=8765, help="Puerto local (por defecto: 8765; 0 elige uno libre)")
    parser.add_argument("--no-browser", action="store_true", help="No abrir el navegador automáticamente")
    parser.add_argument("--database", default=str(DEFAULT_DB), help="Ruta a la base de datos SQLite")
    args = parser.parse_args()
    initialize(args.database)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.database))
    except OSError as error:
        print(f"No se pudo iniciar la aplicación: {error}. Prueba con --port 0.", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Botón de desahogo está disponible en {url}", flush=True)
    print("Pulsa Ctrl+C para cerrar la aplicación.", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAplicación cerrada.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
