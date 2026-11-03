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
| `util.py` | URL normalization, dedupe keys, atomic writes, time helpers. |
| `mozlz4.py` | Decoder for Firefox's `mozLz40` LZ4 container. |
| `sources/firefox.py` | Firefox session store and `profiles.ini` discovery. |
| `sources/chromium.py` | SNSS parser for Chrome, Edge, Brave and Chromium. |
| `sources/text.py` | One-URL-per-line importer. |
| `sources/json_source.py` | Snapshot / tab-array importer. |
| `render.py` | Injects the snapshot and preloaded state into `templates/app.html`. |
| `server.py` | `ThreadingHTTPServer`, page/state APIs, `/download`, live update API. |
| `watcher.py` | Polls the session store and appends newly opened tabs. |
| `cli.py` | `import`, `serve`, `export`, `dedupe`, `status`, `sources`. |

## Data files

`tabs.json`

```json
{
  "version": 1,
  "created_at": "2025-01-02T03:04:05+00:00",
  "updated_at": "2025-01-02T03:10:00+00:00",
  "source": "firefox",
  "dedupe": "normalized",
  "duplicates_merged": 12,
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

## Chromium sessions (SNSS)

Chromium keeps open tabs in `<profile>/Sessions/Session_<timestamp>`. The file
is an SNSS journal:

```
"SNSS" | int32 version | command*
command := uint16 size | uint8 id | (size - 1) bytes payload
```

TabFerry only needs two command types:

| ID | Command | Payload |
| --- | --- | --- |
| 6 | `kCommandUpdateTabNavigation` | Pickle: `int32 tab_id`, `int32 index`, `string url`, `string16 title`, … |
| 7 | `kCommandSetSelectedNavigationIndex` | raw `int32 tab_id`, `int32 index` |

`string` is `uint32 byte_length + UTF-8 bytes`, padded to 4 bytes; `string16` is
`uint32 char_count + UTF-16LE`, padded to 4. Command 6 carries a 4-byte Pickle
length header before the fields. Commands 0/2/7/8 are raw 8-byte `int32` pairs.

The importer collects every navigation per tab, then keeps the entry selected by
command 7 (falling back to the highest index). `Tabs_*` is the recently-closed
list and is only used when no `Session_*` exists. Browsers often hold these
files exclusively on Windows, so `_read_session` turns `PermissionError` into a
`SourceError` with an actionable message.

## Deduplication

`util.dedupe_key(url, mode)` defines what counts as the same tab:

| Mode | Key |
| --- | --- |
| `normalized` (default) | `normalize_url`: lowercase scheme/host, no `www.`, no default port, no fragment, no tracking params (`utm_*`, `fbclid`, `gclid`, `ref`, `spm`, …), no trailing slash, sorted query params |
| `url` | everything before `#` |
| `none` | the full URL, so nothing is merged |

`dedupe_tabs(tabs, mode=...)` keeps the first occurrence. The importer stores
the mode and the number of merged tabs on the `Snapshot`; `tabferry dedupe`
applies the same function to an existing snapshot, and the page shows the count
in its header.

## Live updates

`tabferry serve --watch` starts a daemon `Watcher` thread. Every
`--interval` seconds it calls the same source loaders used by `import`,
then hands the result to `App.add_tabs`:

1. normalise each URL with the configured dedupe mode;
2. skip URLs already in the snapshot, duplicates inside the batch, and URLs the
   user explicitly removed (`state.json`);
3. append the rest, set `updated_at`, save `tabs.json` atomically;
4. bump `App.revision`, remember `(revision, payload)` in a bounded history, and
   re-render the page.

The server exposes:

| Route | Returns |
| --- | --- |
| `GET /api/version` | `revision`, `tabs`, `removed`, `updated_at` |
| `GET /api/updates?since=N` | tabs added at revisions greater than `N` |

The page embeds its starting revision and polls `/api/updates` every eight
seconds, appending new rows in place (and showing a toast). If the server was
restarted and the revision went backwards, the page reloads instead.

Chromium keeps its session file open exclusively on Windows; the watcher
converts that to a `SourceError`, logs it once, and retries on the next tick.
`--source auto` merges Firefox and Chromium results, so a locked Chromium file
does not stop Firefox tabs from flowing in.

## Request flow

1. `tabferry import` picks a source, normalises tabs, applies the configured
   dedupe mode (see below) and writes `tabs.json`.
2. `tabferry serve` loads the snapshot and state, renders the page once into
   memory, and starts a threaded HTTP server.
3. The page loads with the tab list embedded. It calls `GET /api/state` and
   hides removed rows. Removing a row sends `POST /api/remove`; the server
   updates `state.json` before responding.
4. `GET /download` re-renders the template with the current removed list baked
   in as `PRELOADED`, so a downloaded copy starts in the same state.

## Offline behaviour

The page is a single HTML file with no external assets. Labels come from a small
`I18N` table (`navigator.language`, overridable with `?lang=zh|en`), so the UI
works in English and Simplified Chinese without a build step.

When opened from `file://` (or when the API is unreachable), `init()` falls back
to:

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
