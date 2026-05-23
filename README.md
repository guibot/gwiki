# Wiki

A lightweight personal wiki.

Self hosted, single-file frontend, Python server, no dependencies.

![Hub view — card grid to pick a sub-wiki](demo/img1-hub.webp)

![Unlocked mode — add new topics or categories](demo/img2-unlocked.webp)

![Topic editor .md format, with save button](demo/img3-editor.webp)

## Stack

- `index.html` — all CSS and JS inline, no build step, no npm
- `server_wiki.py` — Python stdlib HTTP server with a small REST API
- Custom regex Markdown parser (no external library)

## Running

```bash
python3 server_wiki.py
# open http://localhost:8080
```

## Content structure

```
<wiki-root>/
└── <sub-wiki>/
    └── topics/
        └── <category-slug>/
            ├── <topic-slug>.md
            ├── <topic-slug>.html
            └── images/
                └── photo.webp
```

The server auto-detects two modes:

- **Standalone** — a single `topics/` folder at root → goes straight to the wiki
- **Hub** — multiple sub-wikis at root → shows a card grid to pick one

Category and topic names are derived from folder/file slugs (hyphens → spaces, words capitalised). No config files needed.

## Topic formats

Both `.md` and `.html` files are supported. Format is chosen when creating a new topic. HTML topics open a WYSIWYG editor in admin mode.

## Access modes

| Mode | URL | Description |
|------|-----|-------------|
| Viewer | `/` | Read-only, no edit controls |
| Admin | `/?admin` | Shows unlock button, enables editing |

## Editing

Add `?admin` to the URL to show the lock icon. Click it to unlock edit mode. Clicking any topic opens an inline editor. Save writes directly back to the file.

**Markdown topics** — split-pane editor with live preview.

**HTML topics** — WYSIWYG editor with toolbar: bold, italic, underline, headings, lists, links, image upload. Images can be resized by clicking and dragging the corner handles. Paste an image from clipboard to upload it directly.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/topics[?wiki=]` | Category/topic tree |
| `GET` | `/api/topic?cat=&slug=[&wiki=]` | Raw file content + type |
| `PUT` | `/api/topic?cat=&slug=[&wiki=]` | Save content |
| `POST` | `/api/topic` | Create topic (`name`, `type`: `md`\|`html`) |
| `POST` | `/api/category` | Create category |
| `POST` | `/api/wiki` | Create sub-wiki (hub mode) |
| `POST` | `/api/image?cat=&filename=[&wiki=]` | Upload image (raw binary body) |
| `DELETE` | `/api/topic?cat=&slug=[&wiki=]` | Delete topic |
