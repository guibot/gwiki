# Topic & Category Reorder — Design Spec

**Date:** 2026-06-30  
**Scope:** Drag-and-drop reordering of topics within categories, and categories within the sidebar. Admin-only.

---

## 1. Data Persistence

Order is persisted via `order.json` files alongside content:

- **Topics order:** `topics/<cat-slug>/order.json` — array of topic slugs: `["slug1", "slug2", ...]`
- **Categories order:** `topics/order.json` — array of category slugs: `["cat-slug1", "cat-slug2", ...]`

`get_categories()` reads each `order.json` if present, sorts known slugs by position, then appends any unlisted slugs at the end. Unrecognized slugs (deleted topics/categories) are silently ignored.

### API Endpoint

`PUT /api/order` — requires admin auth (same as existing PUT topic).

Query params:
- `type=topics&cat=<slug>[&wiki=<wiki>]` — reorder topics in a category
- `type=categories[&wiki=<wiki>]` — reorder categories

Body: JSON array of slugs `["slug1", "slug2", ...]`

Response: `200 OK` on success, `400` for bad input, `403` for missing auth.

---

## 2. Frontend Drag UX

Drag-and-drop uses the native HTML5 Drag API. Active only when `body.unlocked` (admin mode).

### Topics

- Each `.nav-item` gets `draggable="true"` when unlocked
- `dragstart`: store `{catSlug, topicSlug, index}` in drag state
- `dragover`: show 2px accent-colored drop indicator line between items; `preventDefault()` to allow drop
- `drop`: reorder local `categories` array → call `PUT /api/order` → rebuild sidebar
- Cross-category drag: drops outside source category are ignored

### Categories

- Each `.nav-category-header` gets `draggable="true"` when unlocked
- Same pattern: `dragstart` stores `catSlug`, `drop` reorders `categories` array → `PUT /api/order`

### Visual Feedback

- Dragged item: 50% opacity during drag
- Drop target: 2px accent-colored indicator line between items (injected div, removed on `dragleave`/`drop`)
- Optimistic local update — sidebar rebuilds immediately; server write happens in background

---

## 3. Error Handling & Edge Cases

| Scenario | Behavior |
|----------|----------|
| `PUT /api/order` fails | Show brief error toast, revert local array to pre-drag state, rebuild sidebar |
| Drag topic across categories | Ignored — drop outside source category has no effect |
| Single-topic category | Drag is a no-op (nothing to reorder) |
| New topic/category created | Appended to end; `order.json` updated on next successful drag |
| `order.json` deleted manually | Falls back to filename sort seamlessly |
| Non-admin user | `draggable` attribute not set; endpoint returns `403` |
