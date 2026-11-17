"""Cliente somente leitura e sincronização FreshRSS → observações OSINT."""

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from globalosint.database import connect, initialize
from globalosint.models import SourceInput, SourceKind
from globalosint.registry import add_source


class FreshRSSError(RuntimeError):
    """Erro de configuração, autenticação ou resposta do FreshRSS."""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    return unescape(" ".join(parser.parts)).strip()


def _first_link(value) -> str:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("href"):
                return str(item["href"])
    if isinstance(value, dict):
        return str(value.get("href", ""))
    return ""


def _published(value) -> str | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            timestamp = float(value)
            if timestamp > 10_000_000_000:  # FreshRSS may expose milliseconds for crawlTimeMsec.
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


class FreshRSSClient:
    """Implementa ClientLogin e os endpoints de leitura da Google Reader API."""

    def __init__(self, api_url: str, username: str, password: str, timeout: int = 20, opener=None):
        self.api_url = api_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.opener = opener or urlopen
        self._auth: str | None = None
        parsed = urlparse(self.api_url)
        local_http = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local_http):
            raise FreshRSSError("FRESHRSS_API_URL deve usar HTTPS (HTTP só é aceito para localhost)")
        if not parsed.netloc or not parsed.path:
            raise FreshRSSError("FRESHRSS_API_URL deve apontar para /api/greader.php")

    @classmethod
    def from_environment(cls):
        api_url = os.environ.get("FRESHRSS_API_URL", "").strip()
        username = os.environ.get("FRESHRSS_USERNAME", "").strip()
        password = os.environ.get("FRESHRSS_PASSWORD", "")
        if not api_url or not username or not password:
            raise FreshRSSError(
                "Configure FRESHRSS_API_URL, FRESHRSS_USERNAME e FRESHRSS_PASSWORD no ambiente"
            )
        return cls(api_url, username, password)

    def _open(self, request: Request):
        try:
            return self.opener(request, timeout=self.timeout)
        except HTTPError as exc:
            if exc.code == 401:
                raise FreshRSSError("FreshRSS recusou a autenticação; confira usuário e senha de API") from None
            raise FreshRSSError(f"FreshRSS respondeu HTTP {exc.code}") from None
        except URLError as exc:
            raise FreshRSSError(f"Não foi possível conectar ao FreshRSS: {exc.reason}") from None
        except TimeoutError:
            raise FreshRSSError("Tempo limite ao consultar o FreshRSS") from None

    def _login(self) -> str:
        payload = urlencode({"Email": self.username, "Passwd": self.password}).encode("utf-8")
        request = Request(
            f"{self.api_url}/accounts/ClientLogin", data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "GLOBAL-OSINT/0.1"},
            method="POST",
        )
        with self._open(request) as response:
            text = response.read(64 * 1024).decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("Auth=") and line[5:].strip():
                self._auth = line[5:].strip()
                return self._auth
        raise FreshRSSError("FreshRSS não retornou um token Auth válido")

    def _get_json(self, path: str, params: dict | None = None) -> dict:
        auth = self._auth or self._login()
        query = urlencode({"output": "json", **(params or {})})
        request = Request(
            f"{self.api_url}/reader/api/0/{path}?{query}",
            headers={"Authorization": f"GoogleLogin auth={auth}", "Accept": "application/json", "User-Agent": "GLOBAL-OSINT/0.1"},
        )
        with self._open(request) as response:
            payload = response.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            raise FreshRSSError("A resposta do FreshRSS excedeu o limite de 8 MiB")
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise FreshRSSError("FreshRSS retornou JSON inválido") from None
        if not isinstance(result, dict):
            raise FreshRSSError("FreshRSS retornou um formato JSON inesperado")
        return result

    def subscriptions(self) -> list[dict]:
        result = self._get_json("subscription/list")
        feeds = result.get("subscriptions", [])
        if not isinstance(feeds, list):
            raise FreshRSSError("A lista de assinaturas do FreshRSS está em formato inesperado")
        return [feed for feed in feeds if isinstance(feed, dict)]

    def entries(self, max_items: int = 500, since_hours: int = 24) -> list[dict]:
        if not 1 <= max_items <= 5000:
            raise ValueError("max_items deve estar entre 1 e 5000")
        if not 1 <= since_hours <= 24 * 90:
            raise ValueError("since_hours deve estar entre 1 e 2160")
        items, continuation = [], None
        newer_than = int(datetime.now(timezone.utc).timestamp()) - since_hours * 3600
        while len(items) < max_items:
            page_size = min(100, max_items - len(items))
            params = {"n": page_size, "ot": newer_than}
            if continuation:
                params["c"] = continuation
            result = self._get_json("stream/contents/reading-list", params)
            page = result.get("items", [])
            if not isinstance(page, list):
                raise FreshRSSError("A lista de artigos do FreshRSS está em formato inesperado")
            items.extend(item for item in page if isinstance(item, dict))
            continuation = result.get("continuation")
            if not continuation or not page:
                break
        return items[:max_items]


def _normalize_item(item: dict) -> dict | None:
    url = _first_link(item.get("canonical")) or _first_link(item.get("alternate"))
    parsed = urlparse(url)
    title = _plain_text(item.get("title"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not title:
        return None
    summary = item.get("summary") or item.get("content")
    summary_text = _plain_text(summary.get("content")) if isinstance(summary, dict) else _plain_text(summary)
    origin = item.get("origin") if isinstance(item.get("origin"), dict) else {}
    external_id = str(item.get("id") or "").strip() or url
    published = _published(item.get("published") or item.get("crawlTimeMsec"))
    digest = sha256(f"{url}\n{title}\n{summary_text}".encode("utf-8")).hexdigest()
    return {
        "external_id": external_id, "url": url, "title": title, "summary": summary_text[:4000] or None,
        "published_at": published, "content_hash": digest,
        "origin_stream_id": str(origin.get("streamId", "")),
        "origin_url": str(origin.get("htmlUrl", "")),
        "origin_title": _plain_text(str(origin.get("title", ""))),
    }


def _source_for_feed(connection, feed: dict):
    feed_url = str(feed.get("url", "")).strip()
    title = _plain_text(str(feed.get("title", ""))) or feed_url
    parsed = urlparse(feed_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    row = connection.execute("SELECT id,status FROM sources WHERE url=?", (feed_url,)).fetchone()
    if row:
        return None if row["status"] == "rejected" else row["id"]
    try:
        source = add_source(connection, SourceInput(
            name=title, url=feed_url, kind=SourceKind.OTHER, languages=(), axes=(),
            notes="Descoberta no FreshRSS; revisar tipo, idioma e eixos antes de aprovar.",
        ))
    except Exception as exc:
        # A URL pode ter sido cadastrada em paralelo por outro fluxo.
        row = connection.execute("SELECT id,status FROM sources WHERE url=?", (feed_url,)).fetchone()
        if row:
            return None if row["status"] == "rejected" else row["id"]
        raise exc
    return source.id


def sync_freshrss(client: FreshRSSClient, max_items: int = 500, since_hours: int = 24) -> dict:
    """Importa artigos como observações, sem promovê-los automaticamente a eventos."""
    initialize()
    with closing(connect()) as db:
        cursor = db.execute("INSERT INTO collection_runs(collector) VALUES(?)", ("freshrss",))
        run_id = cursor.lastrowid
        db.commit()
    try:
        subscriptions = client.subscriptions()
        feeds = {str(feed.get("id", "")): feed for feed in subscriptions if feed.get("id")}
        items = client.entries(max_items=max_items, since_hours=since_hours)
        cutoff = datetime.now(timezone.utc).timestamp() - since_hours * 3600
        imported = duplicates = skipped = 0
        with closing(connect()) as db:
            for raw in items:
                item = _normalize_item(raw)
                if not item:
                    skipped += 1
                    continue
                if not item["published_at"] or datetime.fromisoformat(item["published_at"]).timestamp() < cutoff:
                    skipped += 1
                    continue
                feed = feeds.get(item["origin_stream_id"])
                if feed is None and item["origin_url"]:
                    feed = {"url": item["origin_url"], "title": item["origin_title"]}
                if feed is None:
                    skipped += 1
                    continue
                source_id = _source_for_feed(db, feed)
                if source_id is None:
                    skipped += 1
                    continue
                result = db.execute(
                    """INSERT OR IGNORE INTO source_items
                       (source_id,external_id,url,title,summary,published_at,content_hash,origin_group)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (source_id, item["external_id"], item["url"], item["title"], item["summary"],
                    item["published_at"], item["content_hash"], sha256(item["url"].encode("utf-8")).hexdigest()),
                )
                imported += result.rowcount
                duplicates += 1 - result.rowcount
            db.execute(
                """UPDATE collection_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                   status='succeeded',records_seen=? WHERE id=?""",
                (len(items), run_id),
            )
            db.commit()
        return {"run_id": run_id, "records_seen": len(items), "imported": imported,
                "duplicates": duplicates, "skipped": skipped}
    except Exception as exc:
        with closing(connect()) as db:
            db.execute(
                """UPDATE collection_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                   status='failed',error_summary=? WHERE id=?""",
                (str(exc)[:1000], run_id),
            )
            db.commit()
        raise


def sync_from_environment(max_items: int = 500, since_hours: int = 24) -> dict:
    return sync_freshrss(FreshRSSClient.from_environment(), max_items=max_items, since_hours=since_hours)
