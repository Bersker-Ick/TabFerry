# Architecture

TabFerry is a small pipeline: **import → snapshot → render → serve**.

```
                 ┌──────────────┐
 browser data ──▶│   sources/   │──▶  List[Tab]  ──▶  snapshot.py  ──▶  tabs.json
                 └──────────────┘                                         │
                                                                          ▼
 phone ◀── HTTP ◀── server.py ◀── render.py ◀── templates/app.html ◀── Snapshot
                        │
                        └── state.py ──▶ state.json   (removed URLs)
```

## Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Per-user data directory, `tabs.json` / `state.json` paths. |
| `models.py` | `Tab` (url, title, window, pinned, source) and `Snapshot`. |
| `snapshot.py` | Load/save the imported tab list, with friendly errors. |
| `state.py` | Thread-safe removed-URL set, atomic JSON writes. |
| `mozlz4.py` | Decoder for Firefox's `mozLz40` LZ4 container. |
| `sources/` | Import adapters. `firefox.py`, `text.py`, `json_source.py`. |
| `render.py` | Injects the snapshot and preloaded state into `templates/app.html`. |
| `server.py` | `ThreadingHTTPServer`, static page, JSON state API, `/download`. |
| `cli.py` | `import`, `serve`, `export`, `status`, `sources`. |

## Data files

`tabs.json`

```json
{
  "version": 1,
  "created_at": "2025-01-02T03:04:05+00:00",
  "source": "firefox",
  "tabs": [{"url": "https://example.com/", "title": "Example", "window": 1,
            "pinned": false, "source": "firefox"}]
}
```

`state.json`

```json
{
  "version": 1,
  "updated": "2025-01-02T03:04:05+00:00",
  "removed": {"https://example.com/": "2025-01-02T03:04:05+00:00"}
}
```

Both writes go through `util.atomic_write_text` (temp file, `fsync`, `replace`),
so a crash mid-write cannot leave a half-written JSON document.

## Request flow

1. `tabferry import` picks a source, normalises tabs, deduplicates by URL
   (ignoring `#fragment`) and writes `tabs.json`.
2. `tabferry serve` loads the snapshot and state, renders the page once into
   memory, and starts a threaded HTTP server.
3. The page loads with the tab list embedded. It calls `GET /api/state` and
   hides removed rows. Removing a row sends `POST /api/remove`; the server
   updates `state.json` before responding.
4. `GET /download` re-renders the template with the current removed list baked
   in as `PRELOADED`, so a downloaded copy starts in the same state.

## Offline behaviour

The page is a single HTML file with no external assets. When opened from
`file://` (or when the API is unreachable), `init()` falls back to:

1. `PRELOADED` — state baked in at download time.
2. `localStorage["tabferry:<data-id>:removed"]` — later changes on that device.

Changes are written to `localStorage` on every mutation. When a served page
finds local removals that the server does not know about, it pushes them with
`POST /api/remove`, so offline work is not lost on reconnect.

## Adding a browser

Implement:

```python
from tabferry.sources.base import TabSource
from tabferry.models import Tab

class MyBrowserSource(TabSource):
    name = "mybrowser"
    description = "My Browser session files"

    def load(self) -> list[Tab]:
        ...
```

Register it in `tabferry/sources/__init__.py`; the CLI picks it up
automatically (`--source mybrowser`). Keep browser-specific file formats in
`tabferry/sources/`; the core should not learn about them.

## Design constraints

- **Standard library only** at runtime. This keeps `pipx install` and the
  Docker image tiny, and makes the project easy to audit.
- **No database.** Two JSON files are enough for one user and make backup a
  copy-paste.
- **No auth.** Hosting beyond a trusted network is a reverse-proxy concern;
  documented in the README.
