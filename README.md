# TabFerry

> Ferry your browser tabs to your phone — offline-ready, triageable, self-hosted.

TabFerry reads the tabs you already have open in a desktop browser, builds a
single-file mobile page and serves it on your LAN. Open the page on your phone,
tap through the list, and remove what you have dealt with. Download the offline
copy and the list keeps working when the computer is off; the server stores
removals so they survive restarts.

```
Firefox session  ──import──▶  tabs.json  ──serve──▶  phone (search / open / remove)
                                   │
                                   └──export──▶  standalone HTML (offline)
```

## Features

- **One-command import** — Firefox session store out of the box, plus plain
  text and JSON for everything else.
- **Mobile-first page** — search, tap a title to open, tap `×` to remove.
- **Offline copy** — one self-contained HTML file, no server required.
- **Durable state** — removals are written to `state.json` atomically.
- **Zero runtime dependencies** — pure Python standard library.
- **Self-hosted** — a single small HTTP server; Docker and systemd friendly.
- **Extensible** — add a browser by implementing one class.

## Quick start

```bash
pipx install git+https://github.com/Bersker-Ick/TabFerry.git
tabferry import     # auto-detects your Firefox profile
tabferry serve      # prints the LAN URL
```

Open the printed URL on your phone (same Wi-Fi). Without pipx:

```bash
git clone https://github.com/Bersker-Ick/TabFerry.git
cd TabFerry
python -m pip install .
tabferry import
tabferry serve --host 0.0.0.0 --port 8123
```

Python 3.9 or newer is required.

## Usage

### Import

```bash
tabferry import                                   # newest Firefox session
tabferry import --profile ~/.mozilla/firefox/abc.default
tabferry import --source text --from urls.txt
tabferry import --source json --from tabs.json
tabferry import --keep-duplicates
```

- **Firefox** — reads `sessionstore.jsonlz4` (and the newer
  `sessionstore-backups/recovery.jsonlz4`), discovers profiles through
  `profiles.ini` on Windows, macOS, Linux, Flatpak and Snap.
- **Text** — one URL per line, or `Title<TAB>URL`.
- **JSON** — a TabFerry snapshot or an array of `{"url": "...", "title": "..."}`.

Duplicate pages (same URL, different `#anchor`) are merged by default.

### Serve

```bash
tabferry serve                     # 0.0.0.0:8123
tabferry serve --port 9000
tabferry serve --open              # also open the local browser
```

| Route | Purpose |
| --- | --- |
| `GET /` | the mobile app |
| `GET /api/state` | removed URLs |
| `POST /api/remove` | body `{"url": "..."}` |
| `POST /api/restore` | body `{"url": "..."}` |
| `POST /api/restore_all` | clear removed state |
| `GET /download` | standalone HTML with current state baked in |
| `GET /health` | health probe |

### Export

```bash
tabferry export --format html -o tabferry.html
tabferry export --format txt -o urls.txt
tabferry export --format json
```

### Status

```bash
tabferry status
```

```
Data dir: /home/me/.local/share/tabferry
Created:  2025-01-02T03:04:05+00:00
Source:   firefox
Tabs:     128
Removed:  3
```

## Data

Per-user data directory:

| Platform | Directory |
| --- | --- |
| Windows | `%APPDATA%\TabFerry` |
| macOS | `~/Library/Application Support/TabFerry` |
| Linux | `$XDG_DATA_HOME/tabferry` or `~/.local/share/tabferry` |

Override with `--data-dir` or `TABFERRY_DATA_DIR`. Two files live there:

```
tabs.json    snapshot: tabs, created_at, source
state.json   removed URLs with timestamps
```

## Offline mode

Tap **Save offline copy** in the page header, or run
`tabferry export --format html`. The file is self-contained: the tab list is
embedded and removals live in the browser's `localStorage`.

- Opening it from `file://` works without any server.
- **Export** / **Import** in the *Removed* drawer moves state between the
  offline copy and another device.
- When the page is served by TabFerry, removals are stored server-side in
  `state.json` instead.

## Supported sources

| Source | Flag | Notes |
| --- | --- | --- |
| Firefox | `--source firefox` | session store, profiles.ini discovery |
| Text | `--source text` | one URL per line, optional `Title<TAB>URL` |
| JSON | `--source json` | snapshot or array of tabs |

To add a source, subclass `tabferry.sources.base.TabSource`, implement
`load()`, and register the class in `tabferry/sources/__init__.py`. The
`TabSource` contract is deliberately small so browser-specific code stays out
of the core.

## Deployment

### Docker

```bash
tabferry import --data-dir ./data      # run on the host, where the browser lives
docker compose up -d --build
```

`docker-compose.yml` mounts `./data` at `/data` and restarts on failure.

### systemd

```ini
[Unit]
Description=TabFerry
After=network-online.target

[Service]
ExecStart=/usr/local/bin/tabferry serve --host 0.0.0.0 --port 8123
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Reverse proxy

TabFerry speaks plain HTTP. If you expose it beyond your LAN, terminate TLS and
add authentication at Caddy/Nginx — the built-in server has no auth.

## Security

The server has **no authentication** and the state API is open to anyone who can
reach the port. Run it on a trusted network, or put it behind an authenticated
reverse proxy. The tab list is sensitive: it is everything you had open.

## Development

```bash
git clone https://github.com/Bersker-Ick/TabFerry.git
cd TabFerry
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
ruff check .
```

```
tabferry/
  cli.py          import / serve / export / status / sources
  config.py       per-user data directory and paths
  models.py       Tab, Snapshot
  snapshot.py     snapshot load/save
  state.py        removed-URL store (atomic JSON)
  mozlz4.py       pure-Python mozLz40/LZ4 decompressor
  render.py       template + data -> single-file app
  server.py       HTTP server + JSON API
  sources/        firefox.py, text.py, json_source.py
  templates/      app.html
tests/            unittest suite, no third-party deps
docs/             architecture notes
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the request flow and
extension points.

## Roadmap

- Chromium/Edge open-tab adapter (SNSS parsing).
- Optional access token for the HTTP API.
- A sync endpoint so offline copies can reconcile automatically.
- UI localisation (English today).

## License

MIT © 2025 Bersker-Ick
