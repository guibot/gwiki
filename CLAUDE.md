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
| PUT | `/api/topic?cat=&slug=[&wiki=]` | Save content (detects extension from existing file) |
| POST | `/api/topic` | Create topic — body: `{name, type, cat, wiki}` |
| POST | `/api/category` | Create category |
| POST | `/api/wiki` | Create sub-wiki (hub mode) |
| POST | `/api/image?cat=&filename=[&wiki=]` | Upload image — raw binary body, saves to `topics/<cat>/images/` |
| DELETE | `/api/topic?cat=&slug=[&wiki=]` | Delete topic |

### Security

`safe_path()` blocks path traversal — always use it before touching the filesystem. Image filenames are sanitized with `re.sub(r"[^a-zA-Z0-9._-]", "_", filename)`.

### Access modes

- Viewer: `/` — read-only
- Admin: `/?admin` — shows lock icon, enables edit mode
