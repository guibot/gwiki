# Topic & Category Reorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admins to drag-and-drop topics within categories and categories within the sidebar, with order persisted to `order.json` files.

**Architecture:** `order.json` files sit alongside content (`topics/<cat>/order.json` for topics, `topics/order.json` for categories). Server reads them in `get_categories()` and exposes a new `PUT /api/order` endpoint. Frontend adds HTML5 drag-and-drop to `buildSidebar()`, active only when `body.unlocked`.

**Tech Stack:** Stdlib Python 3.11+, vanilla JS (no libraries), HTML5 Drag API.

## Global Constraints

- No external dependencies — stdlib Python only, no npm, no JS libraries
- `safe_path()` must guard every filesystem operation
- `_write_lock` must wrap every file write
- All admin-gated UI must check `document.body.classList.contains('unlocked')`
- `apiFetch()` handles fetch error throwing — use it for all API calls
- `wikiParam()` returns the `&wiki=...` query string (or `""` in standalone mode)

---

### Task 1: Server — order-aware `get_categories()` + `PUT /api/order`

**Files:**
- Modify: `server_wiki.py:79-97` (`get_categories`)
- Modify: `server_wiki.py:242-307` (`do_PUT`)

**Interfaces:**
- Produces: `PUT /api/order?type=topics&cat=<slug>[&wiki=<wiki>]` — body: JSON array of slug strings, returns `{"ok": true}`
- Produces: `PUT /api/order?type=categories[&wiki=<wiki>]` — same response shape
- `get_categories(topics_dir)` return shape unchanged: `[{slug, display, topics: [{slug, title, type}]}]`

- [ ] **Step 1: Replace `get_categories` with order-aware version**

In `server_wiki.py`, replace the `get_categories` function (lines 79–97) with:

```python
def _apply_order(items: list, order_file: Path) -> list:
    if not order_file.exists():
        return items
    try:
        order = json.loads(order_file.read_text(encoding="utf-8"))
    except Exception:
        return items
    index = {item["slug"]: item for item in items}
    ordered = [index[s] for s in order if s in index]
    seen = {item["slug"] for item in ordered}
    ordered += [item for item in items if item["slug"] not in seen]
    return ordered


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
        topics = _apply_order(topics, cat_dir / "order.json")
        cats.append({
            "slug": cat_dir.name,
            "display": slug_to_display(cat_dir.name),
            "topics": topics,
        })
    cats = _apply_order(cats, topics_dir / "order.json")
    return cats
```

- [ ] **Step 2: Add `PUT /api/order` handler in `do_PUT`**

In `server_wiki.py`, add this block **before** the final `self.send_json({"error": "not found"}, 404)` line at the end of `do_PUT`:

```python
        if parsed.path == "/api/order":
            order_type = qs.get("type", [None])[0]
            wiki = qs.get("wiki", [None])[0]
            cat = qs.get("cat", [None])[0]
            if order_type not in ("topics", "categories"):
                self.send_json({"error": "type must be topics or categories"}, 400)
                return
            if order_type == "topics" and not cat:
                self.send_json({"error": "missing cat"}, 400)
                return
            topics_dir = resolve_topics_dir(self.root, wiki)
            if not topics_dir:
                self.send_json({"error": "wiki not found"}, 404)
                return
            raw = self.read_body()
            try:
                order = json.loads(raw.decode("utf-8"))
                if not isinstance(order, list) or not all(isinstance(s, str) for s in order):
                    raise ValueError
            except Exception:
                self.send_json({"error": "body must be JSON array of strings"}, 400)
                return
            if order_type == "topics":
                order_path = safe_path(topics_dir, cat, "order.json")
            else:
                order_path = safe_path(topics_dir, "order.json")
            if not order_path:
                self.send_json({"error": "invalid path"}, 400)
                return
            with _write_lock:
                order_path.write_text(json.dumps(order), encoding="utf-8")
            self.send_json({"ok": True})
            return
```

- [ ] **Step 3: Manual test — topics order**

Start the server: `python3 server_wiki.py`

Create a test category with 2+ topics, then:

```bash
# Confirm current order
curl -s "http://localhost:8080/api/topics" | python3 -m json.tool

# Write a topics order (replace CAT_SLUG and slugs with real values)
curl -s -X PUT "http://localhost:8080/api/order?type=topics&cat=CAT_SLUG" \
  -H "Content-Type: application/json" \
  -d '["slug2","slug1"]'
# Expected: {"ok": true}

# Confirm new order returned
curl -s "http://localhost:8080/api/topics" | python3 -m json.tool
# Expected: slug2 appears before slug1 in that category
```

- [ ] **Step 4: Manual test — categories order**

```bash
# Write categories order (replace with real category slugs)
curl -s -X PUT "http://localhost:8080/api/order?type=categories" \
  -H "Content-Type: application/json" \
  -d '["cat-slug-2","cat-slug-1"]'
# Expected: {"ok": true}

curl -s "http://localhost:8080/api/topics" | python3 -m json.tool
# Expected: cat-slug-2 appears first in categories array
```

- [ ] **Step 5: Manual test — fallback when order.json missing**

```bash
# Delete an order.json
rm topics/<cat-slug>/order.json

curl -s "http://localhost:8080/api/topics" | python3 -m json.tool
# Expected: topics return in filename-sorted order (no crash)
```

- [ ] **Step 6: Commit**

```bash
git add server_wiki.py
git commit -m "feat: order-aware get_categories and PUT /api/order endpoint"
```

---

### Task 2: Frontend — drag indicator CSS + `saveOrder` helper

**Files:**
- Modify: `index.html` (CSS block, around line 99)
- Modify: `index.html` (JS block, around line 662)

**Interfaces:**
- Produces: CSS classes `.drag-over-before` and `.drag-over-after` — 2px accent line above/below item
- Produces: `let _dragState` module-level variable — holds `{kind, catSlug?, topicIdx?, catIdx?}` during drag; `null` otherwise
- Produces: `async function saveOrder(type, slugs, catSlug)` — calls `PUT /api/order`, throws on failure

- [ ] **Step 1: Add drag indicator CSS**

In `index.html`, after the `.nav-add-category:hover` rule (around line 99), add:

```css
    body.unlocked .nav-item[draggable],
    body.unlocked .nav-category[draggable] { cursor: grab; }
    body.unlocked .nav-item[draggable]:active,
    body.unlocked .nav-category[draggable]:active { cursor: grabbing; }
    .nav-item.dragging, .nav-category.dragging { opacity: 0.4; }
    .drag-indicator {
      height: 2px; background: var(--accent); border-radius: 1px;
      margin: 0 18px; pointer-events: none;
    }
```

- [ ] **Step 2: Add `_dragState` variable and `saveOrder` function**

In `index.html`, after the `apiFetch` function definition (after line 669), add:

```javascript
let _dragState = null;

async function saveOrder(type, slugs, catSlug) {
  const params = new URLSearchParams({ type });
  if (type === 'topics' && catSlug) params.set('cat', catSlug);
  if (activeWiki) params.set('wiki', activeWiki);
  await apiFetch(`/api/order?${params}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(slugs),
  });
}
```

> **Why `_dragState`:** `e.dataTransfer.getData()` returns empty string in `dragover` events (browser security restriction — data only accessible in `drop`). `_dragState` is set in `dragstart` and cleared in `dragend`, making it readable in `dragover` to guard and show the drop indicator.

- [ ] **Step 3: Verify CSS loads without error**

Open `http://localhost:8080` in browser. Open DevTools → Console. Confirm no CSS parse errors. Unlock admin mode — nav items should show `cursor: grab` on hover.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: drag indicator CSS and saveOrder helper"
```

---

### Task 3: Frontend — topic drag-and-drop in `buildSidebar`

**Files:**
- Modify: `index.html` — `buildSidebar` function (around line 1012)

**Interfaces:**
- Consumes: `saveOrder(type, slugs, catSlug)` from Task 2
- Consumes: `categories` global array, `buildSidebar()`, `updateNavActive()`
- Produces: drag-and-drop reorder of topics within a category; calls `PUT /api/order?type=topics`

- [ ] **Step 1: Replace topic item creation in `buildSidebar`**

In `index.html`, find the `cat.topics.forEach(topic => {` block inside `buildSidebar` (around line 1030). Replace the entire `cat.topics.forEach` block with:

```javascript
    cat.topics.forEach((topic, topicIdx) => {
      const item = document.createElement('div');
      item.className = 'nav-item';
      item.dataset.catSlug = cat.slug;
      item.dataset.topicSlug = topic.slug;
      const dot = document.createElement('span');
      dot.className = 'nav-dot';
      item.appendChild(dot);
      item.appendChild(document.createTextNode(topic.title));
      item.addEventListener('click', () => loadTopic({ catSlug: cat.slug, slug: topic.slug, title: topic.title, type: topic.type }));

      if (document.body.classList.contains('unlocked')) {
        item.draggable = true;
        item.addEventListener('dragstart', e => {
          e.dataTransfer.effectAllowed = 'move';
          _dragState = { kind: 'topic', catSlug: cat.slug, topicIdx };
          item.classList.add('dragging');
        });
        item.addEventListener('dragend', () => {
          item.classList.remove('dragging');
          _dragState = null;
        });

        item.addEventListener('dragover', e => {
          if (!_dragState || _dragState.kind !== 'topic' || _dragState.catSlug !== cat.slug) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
          const existing = items.querySelector('.drag-indicator');
          if (existing) existing.remove();
          const rect = item.getBoundingClientRect();
          const mid = rect.top + rect.height / 2;
          const indicator = document.createElement('div');
          indicator.className = 'drag-indicator';
          if (e.clientY < mid) {
            items.insertBefore(indicator, item);
          } else {
            item.after(indicator);
          }
        });

        item.addEventListener('dragleave', () => {
          const existing = items.querySelector('.drag-indicator');
          if (existing) existing.remove();
        });

        item.addEventListener('drop', e => {
          e.preventDefault();
          const existing = items.querySelector('.drag-indicator');
          if (existing) existing.remove();
          const data = _dragState;
          if (!data || data.kind !== 'topic' || data.catSlug !== cat.slug) return;

          const fromIdx = data.topicIdx;
          const rect = item.getBoundingClientRect();
          const mid = rect.top + rect.height / 2;
          let toIdx = e.clientY < mid ? topicIdx : topicIdx + 1;
          if (fromIdx === toIdx || fromIdx === toIdx - 1) return;

          const catObj = categories.find(c => c.slug === cat.slug);
          if (!catObj) return;
          const snapshot = [...catObj.topics];
          const [moved] = catObj.topics.splice(fromIdx, 1);
          const insertAt = toIdx > fromIdx ? toIdx - 1 : toIdx;
          catObj.topics.splice(insertAt, 0, moved);
          buildSidebar();
          updateNavActive();

          saveOrder('topics', catObj.topics.map(t => t.slug), cat.slug).catch(err => {
            catObj.topics = snapshot;
            buildSidebar();
            updateNavActive();
            alert('Erro ao guardar ordem: ' + err.message);
          });
        });
      }

      items.appendChild(item);
    });
```

- [ ] **Step 2: Clear drag indicators on items container dragleave**

After the `cat.topics.forEach` block, before the `addBtn` creation, add:

```javascript
    items.addEventListener('dragleave', e => {
      if (!items.contains(e.relatedTarget)) {
        const existing = items.querySelector('.drag-indicator');
        if (existing) existing.remove();
      }
    });
```

- [ ] **Step 3: Manual test — topic drag-and-drop**

1. Open `http://localhost:8080/?admin` and unlock admin
2. Confirm topics show `cursor: grab` on hover
3. Drag a topic above another — confirm 2px accent line appears as drop indicator
4. Drop — confirm topic moved in sidebar
5. Refresh page — confirm order persisted (check `topics/<cat>/order.json` exists with correct slugs)
6. Drag to same position — confirm no reorder, no error

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: topic drag-and-drop reorder in sidebar"
```

---

### Task 4: Frontend — category drag-and-drop in `buildSidebar`

**Files:**
- Modify: `index.html` — `buildSidebar` function (around line 1016)

**Interfaces:**
- Consumes: `saveOrder(type, slugs, catSlug)` from Task 2
- Consumes: `categories` global array, `buildSidebar()`, `updateNavActive()`
- Produces: drag-and-drop reorder of categories; calls `PUT /api/order?type=categories`

- [ ] **Step 1: Add draggable + drag events to category section**

In `buildSidebar`, find where `section.className = 'nav-category'` is set (around line 1018). After the line `section.dataset.catSlug = cat.slug;`, add:

```javascript
    if (document.body.classList.contains('unlocked')) {
      section.draggable = true;
      section.addEventListener('dragstart', e => {
        if (e.target !== section && !e.target.classList.contains('nav-category-header')) return;
        e.stopPropagation();
        e.dataTransfer.effectAllowed = 'move';
        _dragState = { kind: 'category', catIdx };
        section.classList.add('dragging');
      });
      section.addEventListener('dragend', () => {
        section.classList.remove('dragging');
        _dragState = null;
        const existing = nav.querySelector('.drag-indicator');
        if (existing) existing.remove();
      });

      section.addEventListener('dragover', e => {
        if (!_dragState || _dragState.kind !== 'category') return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'move';
        const existing = nav.querySelector('.drag-indicator');
        if (existing) existing.remove();
        const rect = section.getBoundingClientRect();
        const mid = rect.top + rect.height / 2;
        const indicator = document.createElement('div');
        indicator.className = 'drag-indicator';
        if (e.clientY < mid) {
          nav.insertBefore(indicator, section);
        } else {
          section.after(indicator);
        }
      });

      section.addEventListener('dragleave', e => {
        if (!section.contains(e.relatedTarget)) {
          const existing = nav.querySelector('.drag-indicator');
          if (existing) existing.remove();
        }
      });

      section.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        const existing = nav.querySelector('.drag-indicator');
        if (existing) existing.remove();
        const data = _dragState;
        if (!data || data.kind !== 'category') return;

        const fromIdx = data.catIdx;
        const rect = section.getBoundingClientRect();
        const mid = rect.top + rect.height / 2;
        let toIdx = e.clientY < mid ? catIdx : catIdx + 1;
        if (fromIdx === toIdx || fromIdx === toIdx - 1) return;

        const snapshot = [...categories];
        const [moved] = categories.splice(fromIdx, 1);
        const insertAt = toIdx > fromIdx ? toIdx - 1 : toIdx;
        categories.splice(insertAt, 0, moved);
        buildSidebar();
        updateNavActive();

        saveOrder('categories', categories.map(c => c.slug)).catch(err => {
          categories.splice(0, categories.length, ...snapshot);
          buildSidebar();
          updateNavActive();
          alert('Erro ao guardar ordem: ' + err.message);
        });
      });
    }
```

Note: the `categories.forEach((cat, catIdx) => {` loop variable is `catIdx` — confirm this matches the actual variable name in the existing loop. If it's unnamed (e.g., `categories.forEach(cat => {`), change it to `categories.forEach((cat, catIdx) => {`.

- [ ] **Step 2: Verify topic drag doesn't trigger category handlers**

No code change needed. Category `dragover` guard is `if (!_dragState || _dragState.kind !== 'category') return` — when a topic is being dragged, `_dragState.kind === 'topic'`, so the category handler exits immediately. Confirm this by dragging a topic and verifying no category-level drop indicator appears.

- [ ] **Step 3: Manual test — category drag-and-drop**

1. Open `http://localhost:8080/?admin`, unlock admin, ensure 2+ categories exist
2. Drag a category header — confirm 2px accent line appears between categories
3. Drop — confirm category moved in sidebar
4. Refresh — confirm order persisted (check `topics/order.json`)
5. Drag category while a topic drag is in progress should not be possible (draggable only set when unlocked, and dragstart guard on `e.target`)

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: category drag-and-drop reorder in sidebar"
```

---

### Task 5: Restore demo files + integration + push

**Files:**
- Restore: `demo/img2-unlocked.webp`, `demo/img3-editor.webp`, `demo/topics/01-getting-started/01-welcome.md`, `demo/topics/01-getting-started/img1.webp`, `demo/topics/01-getting-started/img2.png`, `demo/topics/02-markdown-guide/01-syntax.md`

**Interfaces:**
- None — cleanup task

- [ ] **Step 1: Restore deleted demo files**

```bash
git restore demo/img2-unlocked.webp demo/img3-editor.webp \
  demo/topics/01-getting-started/01-welcome.md \
  demo/topics/01-getting-started/img1.webp \
  demo/topics/01-getting-started/img2.png \
  demo/topics/02-markdown-guide/01-syntax.md
```

- [ ] **Step 2: Verify no unintended changes staged**

```bash
git status
```

Expected: only the restored demo files show as changes (if any — `git restore` from HEAD means they should be clean). Local content files must NOT appear (they are gitignored).

- [ ] **Step 3: Full integration test**

1. `python3 server_wiki.py`
2. Open `http://localhost:8080/?admin`, unlock
3. Reorder topics → refresh → confirm persists
4. Reorder categories → refresh → confirm persists
5. Delete `topics/order.json` → refresh → confirm fallback to filename order
6. Check `http://localhost:8080` (viewer, no admin) — confirm drag cursor not shown, drag has no effect

- [ ] **Step 4: Commit restored demo files**

```bash
git add demo/
git commit -m "chore: restore demo files"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```
