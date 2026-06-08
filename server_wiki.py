#!/usr/bin/env python3
"""
Wiki HTTP server — stdlib only.
Configure WIKI_PATH below, then: python3 server.py
"""
import hashlib
import hmac
import json
import re
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

WIKI_PATH = "./"
PORT = 8080


def safe_path(base: Path, *parts: str) -> Path | None:
    if any(".." in p for p in parts):
        return None
    try:
        joined = base
        for part in parts:
            joined = joined / part
        resolved = joined.resolve()
        if str(resolved).startswith(str(base.resolve())):
            return resolved
        return None
    except Exception:
        return None


def slug_to_display(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())


def extract_title(text: str, slug: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return slug_to_display(slug)


def to_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9\-_]", "", name.strip().lower().replace(" ", "-"))


def is_hub_mode(root: Path) -> bool:
    return not (root / "topics").exists()


def get_wikis(root: Path) -> list:
    wikis = []
    for item in sorted(root.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        topics_dir = item / "topics"
        if topics_dir.exists():
            cat_count = sum(
                1 for c in topics_dir.iterdir()
                if c.is_dir() and not c.name.startswith(".")
            )
            wikis.append({
                "name": item.name,
                "display": slug_to_display(item.name),
                "catCount": cat_count,
            })
    return wikis


def get_categories(topics_dir: Path) -> list:
    cats = []
    for cat_dir in sorted(topics_dir.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith("."):
            continue
        topics = []
        for f in sorted(cat_dir.iterdir()):
            if f.suffix not in (".md", ".html") or f.name.startswith("."):
                continue
            slug = f.stem
            text = f.read_text(encoding="utf-8")
            ftype = "html" if f.suffix == ".html" else "md"
            topics.append({"slug": slug, "title": extract_title(text, slug), "type": ftype})
        cats.append({
            "slug": cat_dir.name,
            "display": slug_to_display(cat_dir.name),
            "topics": topics,
        })
    return cats


def resolve_topics_dir(root: Path, wiki: str | None) -> Path | None:
    if is_hub_mode(root):
        if not wiki:
            return None
        p = safe_path(root, wiki, "topics")
        return p if p and p.exists() else None
    else:
        p = root / "topics"
        return p if p.exists() else None


class WikiHandler(BaseHTTPRequestHandler):
    root = Path(WIKI_PATH).resolve()

    def log_message(self, format, *args):
        if self.command in ("PUT", "POST", "DELETE"):
            print(f"[{self.command}] {self.path} → {args[1] if len(args) > 1 else '?'}")

    def read_body(self) -> bytes:
        te = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                if not size_line:
                    break
                size = int(size_line, 16)
                if size == 0:
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.read(2)  # CRLF after chunk
            return b"".join(chunks)
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path):
        import mimetypes
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path

        if path == "/":
            index = self.root / "index.html"
            if index.exists():
                self.send_file(index)
            else:
                self.send_json({"error": "index.html not found"}, 404)
            return

        if path == "/api/topics":
            wiki = qs.get("wiki", [None])[0]
            if is_hub_mode(self.root) and not wiki:
                self.send_json({"mode": "hub", "wikis": get_wikis(self.root)})
                return
            topics_dir = resolve_topics_dir(self.root, wiki)
            if not topics_dir:
                self.send_json({"error": "wiki not found"}, 404)
                return
            self.send_json({"mode": "standalone", "categories": get_categories(topics_dir)})
            return

        if path == "/api/topic":
            wiki = qs.get("wiki", [None])[0]
            cat = qs.get("cat", [None])[0]
            slug = qs.get("slug", [None])[0]
            if not cat or not slug:
                self.send_json({"error": "missing cat or slug"}, 400)
                return
            topics_dir = resolve_topics_dir(self.root, wiki)
            if not topics_dir:
                self.send_json({"error": "wiki not found"}, 404)
                return
            md_path = safe_path(topics_dir, cat, slug + ".md")
            html_path = safe_path(topics_dir, cat, slug + ".html")
            if md_path and md_path.exists():
                ftype, file_path = "md", md_path
            elif html_path and html_path.exists():
                ftype, file_path = "html", html_path
            else:
                self.send_json({"error": "topic not found"}, 404)
                return
            self.send_json({"content": file_path.read_text(encoding="utf-8"), "type": ftype})
            return

        if path == "/api/auth":
            bfly = self.root / ".butterfly"
            token = qs.get("token", [None])[0]
            if token:
                if not bfly.exists():
                    self.send_json({"ok": False})
                    return
                _, stored = bfly.read_text().strip().split(":", 1)
                expected = hmac.new(stored.encode(), b"gwiki-admin", hashlib.sha256).hexdigest()
                self.send_json({"ok": token == expected})
                return
            self.send_json({"setup": not bfly.exists()})
            return

        file_path = safe_path(self.root, path.lstrip("/"))
        if file_path and file_path.exists() and file_path.is_file():
            self.send_file(file_path)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/topic":
            wiki = qs.get("wiki", [None])[0]
            cat = qs.get("cat", [None])[0]
            slug = qs.get("slug", [None])[0]
            if not cat or not slug:
                self.send_json({"error": "missing cat or slug"}, 400)
                return
            topics_dir = resolve_topics_dir(self.root, wiki)
            if not topics_dir:
                self.send_json({"error": "wiki not found"}, 404)
                return
            md_path = safe_path(topics_dir, cat, slug + ".md")
            html_path = safe_path(topics_dir, cat, slug + ".html")
            if not md_path:
                self.send_json({"error": "invalid path"}, 400)
                return
            if html_path and html_path.exists():
                file_path = html_path
            else:
                file_path = md_path
            raw = self.read_body()
            if not raw:
                self.send_json({"error": "empty body"}, 400)
                return
            content = raw.decode("utf-8")
            file_path.write_text(content, encoding="utf-8")
            self.send_json({"ok": True})
            return

        if parsed.path == "/api/description":
            wiki = qs.get("wiki", [None])[0]
            if is_hub_mode(self.root):
                if not wiki:
                    self.send_json({"error": "missing wiki"}, 400)
                    return
                target_dir = safe_path(self.root, wiki)
                if not target_dir or not target_dir.exists():
                    self.send_json({"error": "wiki not found"}, 404)
                    return
            else:
                target_dir = self.root
            raw = self.read_body()
            content = raw.decode("utf-8").strip()
            (target_dir / "description.txt").write_text(content, encoding="utf-8")
            self.send_json({"ok": True})
            return

        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/image":
            cat = qs.get("cat", [None])[0]
            filename = qs.get("filename", [None])[0]
            wiki = qs.get("wiki", [None])[0]
            if not filename:
                self.send_json({"error": "missing filename"}, 400)
                return
            safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
            raw = self.read_body()
            if not raw:
                self.send_json({"error": "empty body"}, 400)
                return

            if cat:
                topics_dir = resolve_topics_dir(self.root, wiki)
                if not topics_dir:
                    self.send_json({"error": "wiki not found"}, 404)
                    return
                cat_dir = safe_path(topics_dir, cat)
                if not cat_dir or not cat_dir.exists():
                    self.send_json({"error": "category not found"}, 404)
                    return
                images_dir = cat_dir / "images"
                images_dir.mkdir(exist_ok=True)
                (images_dir / safe_name).write_bytes(raw)
                prefix = f"/{wiki}/topics/{cat}" if wiki else f"/topics/{cat}"
                self.send_json({"url": f"{prefix}/images/{safe_name}"})
                return

            # No category — store at wiki root, or server root if no wiki given
            if is_hub_mode(self.root) and wiki:
                target_dir = safe_path(self.root, wiki)
                if not target_dir or not target_dir.exists():
                    self.send_json({"error": "wiki not found"}, 404)
                    return
                prefix = f"/{wiki}"
            else:
                target_dir = self.root
                prefix = ""
            (target_dir / safe_name).write_bytes(raw)
            self.send_json({"url": f"{prefix}/{safe_name}"})
            return

        if parsed.path == "/api/auth":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self.send_json({"error": "invalid JSON body"}, 400)
                return
            password = body.get("password", "")
            if not password:
                self.send_json({"error": "missing password"}, 400)
                return
            bfly = self.root / ".butterfly"
            if not bfly.exists():
                salt = secrets.token_hex(16)
                h = hashlib.sha256((salt + password).encode()).hexdigest()
                bfly.write_text(f"{salt}:{h}")
            else:
                salt, stored = bfly.read_text().strip().split(":", 1)
                h = hashlib.sha256((salt + password).encode()).hexdigest()
                if h != stored:
                    self.send_json({"error": "wrong password"}, 401)
                    return
            token = hmac.new(h.encode(), b"gwiki-admin", hashlib.sha256).hexdigest()
            self.send_json({"ok": True, "token": token})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_json({"error": "invalid JSON body"}, 400)
            return

        if parsed.path == "/api/topic":
            wiki = body.get("wiki")
            cat = body.get("cat", "").strip()
            name = body.get("name", "").strip()
            if not cat or not name:
                self.send_json({"error": "missing cat or name"}, 400)
                return
            topics_dir = resolve_topics_dir(self.root, wiki)
            if not topics_dir:
                self.send_json({"error": "wiki not found"}, 404)
                return
            slug = to_slug(name)
            if not slug:
                self.send_json({"error": "invalid name"}, 400)
                return
            cat_dir = safe_path(topics_dir, cat)
            if not cat_dir or not cat_dir.exists():
                self.send_json({"error": "category not found"}, 404)
                return
            ftype = body.get("type", "md")
            ext = ".html" if ftype == "html" else ".md"
            file_path = cat_dir / (slug + ext)
            if file_path.exists():
                self.send_json({"error": "topic already exists"}, 409)
                return
            if ftype == "html":
                content = f"<h1>{name}</h1>\n\n<p>Conteúdo do tópico.</p>\n"
            else:
                content = f"# {name}\n\nConteúdo do tópico.\n"
            file_path.write_text(content, encoding="utf-8")
            self.send_json({"slug": slug, "title": name, "content": content, "type": ftype})
            return

        if parsed.path == "/api/wiki":
            name = body.get("name", "").strip()
            if not name:
                self.send_json({"error": "missing name"}, 400)
                return
            slug = to_slug(name)
            if not slug:
                self.send_json({"error": "invalid name"}, 400)
                return
            wiki_dir = safe_path(self.root, slug)
            if not wiki_dir:
                self.send_json({"error": "invalid path"}, 400)
                return
            if wiki_dir.exists():
                self.send_json({"error": "wiki already exists"}, 409)
                return
            (wiki_dir / "topics").mkdir(parents=True)
            self.send_json({"slug": slug, "display": slug_to_display(slug)})
            return

        if parsed.path == "/api/category":
            wiki = body.get("wiki")
            name = body.get("name", "").strip()
            if not name:
                self.send_json({"error": "missing name"}, 400)
                return
            topics_dir = resolve_topics_dir(self.root, wiki)
            if not topics_dir:
                self.send_json({"error": "wiki not found"}, 404)
                return
            slug = to_slug(name)
            if not slug:
                self.send_json({"error": "invalid name"}, 400)
                return
            cat_dir = safe_path(topics_dir, slug)
            if not cat_dir:
                self.send_json({"error": "invalid path"}, 400)
                return
            if cat_dir.exists():
                self.send_json({"error": "category already exists"}, 409)
                return
            cat_dir.mkdir()
            self.send_json({"slug": slug, "display": slug_to_display(slug)})
            return

        self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/topic":
            wiki = qs.get("wiki", [None])[0]
            cat = qs.get("cat", [None])[0]
            slug = qs.get("slug", [None])[0]
            if not cat or not slug:
                self.send_json({"error": "missing cat or slug"}, 400)
                return
            topics_dir = resolve_topics_dir(self.root, wiki)
            if not topics_dir:
                self.send_json({"error": "wiki not found"}, 404)
                return
            md_path = safe_path(topics_dir, cat, slug + ".md")
            html_path = safe_path(topics_dir, cat, slug + ".html")
            if md_path and md_path.exists():
                file_path = md_path
            elif html_path and html_path.exists():
                file_path = html_path
            else:
                self.send_json({"error": "topic not found"}, 404)
                return
            file_path.unlink()
            self.send_json({"ok": True})
            return

        self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), WikiHandler)
    print(f"Wiki server → http://localhost:{PORT}  (Ctrl+C para parar)")
    print(f"Pasta: {WikiHandler.root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")
