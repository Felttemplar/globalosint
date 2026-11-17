"""Dashboard somente leitura servido localmente."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from globalosint.database import connect, initialize

AXES = {"energy": "Energia", "conflict": "Conflitos", "economy": "Economia", "climate": "Clima e abastecimento", "cyber": "Cibersegurança", "health": "Saúde"}


def _query_one(connection, sql: str, params=()):
    return connection.execute(sql, params).fetchone()[0]


def summary() -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    start = today - timedelta(days=29)
    with closing(connect()) as db:
        metrics = {
            "sources": _query_one(db, "SELECT COUNT(*) FROM sources"),
            "approved_sources": _query_one(db, "SELECT COUNT(*) FROM sources WHERE status='approved'"),
            "candidate_sources": _query_one(db, "SELECT COUNT(*) FROM sources WHERE status='candidate'"),
            "events": _query_one(db, "SELECT COUNT(*) FROM events"),
            "investigating": _query_one(db, "SELECT COUNT(*) FROM events WHERE status='investigating'"),
            "recent_events": _query_one(db, "SELECT COUNT(*) FROM events WHERE date(created_at) >= ?", (start.isoformat(),)),
            "confirmed": _query_one(db, "SELECT COUNT(*) FROM events WHERE status='confirmed'"),
        }
        axis_rows = db.execute("SELECT axis, COUNT(*) n FROM events GROUP BY axis").fetchall()
        day_rows = db.execute(
            "SELECT date(created_at) day, COUNT(*) n FROM events WHERE date(created_at) BETWEEN ? AND ? GROUP BY date(created_at)",
            (start.isoformat(), today.isoformat()),
        ).fetchall()
        latest_run = db.execute(
            "SELECT id, started_at, finished_at, status, collector, records_seen, error_summary FROM collection_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        latest_sources = db.execute(
            "SELECT id,name,kind,status,reliability_score,updated_at FROM sources ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
    axis_counts = {row["axis"]: row["n"] for row in axis_rows}
    day_counts = {row["day"]: row["n"] for row in day_rows}
    days = []
    for offset in range(30):
        day = (start + timedelta(days=offset)).isoformat()
        days.append({"date": day, "count": day_counts.get(day, 0)})
    return {
        "generated_at": now.isoformat(), "metrics": metrics,
        "axes": [{"key": key, "label": label, "count": axis_counts.get(key, 0)} for key, label in AXES.items()],
        "timeline": days, "latest_run": dict(latest_run) if latest_run else None,
        "latest_sources": [dict(row) for row in latest_sources],
    }


def events(query: dict[str, list[str]]) -> list[dict]:
    clauses, params = [], []
    axis, status = query.get("axis", ["all"])[0], query.get("status", ["all"])[0]
    search = query.get("q", [""])[0].strip()
    if axis in AXES:
        clauses.append("axis=?")
        params.append(axis)
    if status in {"investigating", "confirmed", "closed"}:
        clauses.append("status=?")
        params.append(status)
    if search:
        clauses.append("(title LIKE ? OR summary LIKE ? OR location LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = (
        "SELECT id,title,summary,axis,classification,confidence_score,severity,location,occurred_at,status,created_at,updated_at FROM events"
        + where + " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END, updated_at DESC LIMIT 100"
    )
    with closing(connect()) as db:
        return [dict(row) for row in db.execute(sql, params)]


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            content = Path(__file__).with_name("dashboard.html").read_bytes()
            self._send(content, "text/html; charset=utf-8")
        elif parsed.path == "/api/summary":
            self._json(summary())
        elif parsed.path == "/api/events":
            self._json(events(parse_qs(parsed.query)))
        else:
            self.send_error(404)

    def _json(self, value):
        self._send(json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, content, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        print(f"[dashboard] {self.address_string()} {format % args}")


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    initialize()
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"GLOBAL OSINT Dashboard em http://{host}:{port} (somente leitura)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard encerrado.")
    finally:
        server.server_close()
