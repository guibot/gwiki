# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

```bash
python3 server_wiki.py
# open http://localhost:8080
```

No build step, no npm, no dependencies — stdlib Python only.

## Architecture

Two files make up the entire app:

- **`index.html`** — all CSS and JS inline, no external bundler. Custom regex Markdown parser (no library). Handles hub/standalone rendering, sidebar nav, inline editor, admin unlock.
- **`server_wiki.py`** — `http.server`-based REST API. `WIKI_PATH` (default `./`) controls where content is read from. `WikiHandler` handles all routes.

### Server modes

`is_hub_mode(root)` returns `True` when no `topics/` exists at root — switches to multi-wiki hub. Otherwise standalone mode goes straight to the wiki.

### Content layout

```
<wiki-root>/
└── <sub-wiki>/          # hub mode only
    └── topics/
        └── <category-slug>/
            ├── <topic-slug>.md
            ├── <topic-slug>.html
            └── images/
```

Category/topic display names are derived from slugs at read time (`slug_to_display`). No config files.

### Topic formats

Both `.md` and `.html` are supported. `get_categories()` scans both extensions and includes a `type` field (`"md"` or `"html"`) in every topic object. The GET `/api/topic` handler checks `.md` first, then `.html`. The PUT handler writes to whichever extension already exists on disk.

### Frontend rendering

- **MD topics**: `parseMarkdown()` — custom regex parser, no library.
- **HTML topics**: `sanitizeHtml()` — strips `<style>` tags and `color`/`background` inline styles, rewrites relative `images/` src paths to absolute server paths before injecting as `innerHTML`.

`currentTopic.type` must always be set correctly before calling `loadTopic` — pass `type` explicitly in every object passed to `loadTopic` (sidebar clicks, welcome cards, addTopic, saveTopic).

### WYSIWYG editor (HTML topics)

Opened by clicking a topic in unlocked admin mode. Uses `contenteditable`. Toolbar uses `document.execCommand()`. Features:
- B / I / U / H1–H3 / P / UL / OL / Link / IMG / remove format
- Image upload: file picker or clipboard paste → `POST /api/image` → `execCommand('insertImage')`
- Image resize: click image → drag corner handles
- Selection is saved/restored before async link prompt so `createLink` works correctly
- On save, `wysiwyg.cloneNode(true)` is used and image src paths are stripped back to relative before writing

### API routes (all in `server_wiki.py`)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/topics[?wiki=]` | Returns hub list or category tree (topics include `type`) |
| GET | `/api/topic?cat=&slug=[&wiki=]` | File content + `type` |
| GET | `/api/auth[?token=]` | No token: setup status. With `token`: validates it |
| GET | `/api/settings` | Reads `settings.json` (hub title/colors/logo/rotating words) |
| PUT | `/api/topic?cat=&slug=[&wiki=]` | Save content (detects extension from existing file) — auth required |
| PUT | `/api/description?wiki=` | Save `description.txt` — auth required |
| PUT | `/api/settings` | Overwrite `settings.json` — auth required |
| PUT | `/api/order?type=topics\|categories&wiki=&cat=` | Save `order.json` (array of slugs) — auth required |
| PUT | `/api/wiki?wiki=` | Rename sub-wiki (renames folder, re-slugs) — auth required |
| PUT | `/api/label?cat=&wiki=` | Save `label.json` (`name`/`color`) for a category — auth required |
| PUT | `/api/category?cat=&wiki=` | Rename category (renames folder, re-slugs) — auth required |
| POST | `/api/topic` | Create topic — body: `{name, type, cat, wiki}` — auth required |
| POST | `/api/category` | Create category — auth required |
| POST | `/api/wiki` | Create sub-wiki (hub mode) — auth required |
| POST | `/api/image?cat=&filename=[&wiki=]` | Upload image — raw binary body, saves to `topics/<cat>/images/`; omit `cat` to write `cover.webp`/`logo.webp` at wiki/server root — auth required |
| POST | `/api/auth` | body: `{password}` — first call sets the password, later calls verify it; returns a Bearer token |
| DELETE | `/api/topic?cat=&slug=[&wiki=]` | Delete topic — auth required |
| DELETE | `/api/category?cat=&wiki=` | Delete category (recursive) — auth required |

### Security

`safe_path()` blocks path traversal — always use it before touching the filesystem. Image filenames are sanitized with `re.sub(r"[^a-zA-Z0-9._-]", "_", filename)`.

`require_auth()` gates every write route (all of PUT/DELETE, and POST except `/api/auth` itself) — checks an `Authorization: Bearer <token>` header via `hmac.compare_digest` against a token derived from the stored password hash (`check_auth()`/`admin_token()`). Frontend sends this header via `authHeaders()` (`index.html`), reading `admin_token` from `localStorage`. Password itself is salted SHA-256, stored in `.butterfly` at server root.

### Category label editor

In unlocked admin mode, a category can be given a custom display name and color, stored as `label.json` in the category folder (via `PUT /api/label`). The editor modal also renders a QR code (inline vanilla-JS `qrcode` library embedded at the top of `index.html`, no dependency) linking to the category's deep link, and can export the label as JPEG or PDF (`exportLabelJpeg`/`exportLabelPdf`).

### Drag-and-drop / manual ordering

Categories and topics can be reordered by drag-and-drop in unlock mode; order is persisted per-list as `order.json` (array of slugs) via `PUT /api/order?type=topics|categories`.

### Access modes

- Viewer: `/` — read-only
- Admin: `/?admin` — shows lock icon, enables edit mode
