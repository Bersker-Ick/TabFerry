"""Command-line interface for TabFerry."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import resolve_paths
from .models import Snapshot
from .render import render
from .server import App, urls_for
from .snapshot import SnapshotError, load as load_snapshot, save as save_snapshot
from .sources import SOURCES, SourceError, get_source, load_firefox
from .state import StateStore
from .util import dedupe_tabs, now_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tabferry",
        description="Ferry your browser tabs to your phone.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    imp = sub.add_parser("import", help="import tabs into a snapshot")
    imp.add_argument("--source", choices=sorted(SOURCES), default="firefox",
                     help="where tabs come from (default: firefox)")
    imp.add_argument("--profile", help="Firefox profile directory (default: auto-detect)")
    imp.add_argument("--from", dest="from_path", metavar="PATH",
                     help="input file for --source text or json")
    imp.add_argument("--data-dir", help="data directory (default: per-user app data)")
    imp.add_argument("--keep-duplicates", action="store_true",
                     help="keep tabs whose URL differs only by #fragment")
    imp.set_defaults(func=cmd_import)

    serve = sub.add_parser("serve", help="serve the mobile page")
    serve.add_argument("--host", default="0.0.0.0", help="bind address (default: 0.0.0.0)")
    serve.add_argument("--port", type=int, default=8123, help="port (default: 8123)")
    serve.add_argument("--data-dir", help="data directory (default: per-user app data)")
    serve.add_argument("--open", action="store_true", help="open the page in the local browser")
    serve.set_defaults(func=cmd_serve)

    exp = sub.add_parser("export", help="export the snapshot")
    exp.add_argument("--format", choices=["html", "json", "txt"], default="html")
    exp.add_argument("--output", "-o", help="write to this file (default: stdout)")
    exp.add_argument("--data-dir", help="data directory (default: per-user app data)")
    exp.set_defaults(func=cmd_export)

    status = sub.add_parser("status", help="show the current snapshot")
    status.add_argument("--data-dir", help="data directory (default: per-user app data)")
    status.set_defaults(func=cmd_status)

    sources = sub.add_parser("sources", help="list available import sources")
    sources.set_defaults(func=cmd_sources)

    return parser


def cmd_import(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.data_dir).ensure()
    try:
        if args.source == "firefox":
            tabs = load_firefox(args.profile)
            label = "firefox"
        else:
            if not args.from_path:
                print(f"error: --from is required for --source {args.source}", file=sys.stderr)
                return 2
            tabs = get_source(args.source)(args.from_path).load()
            label = f"{args.source}:{Path(args.from_path).name}"
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    raw_count = len(tabs)
    if not args.keep_duplicates:
        tabs = dedupe_tabs(tabs)

    snapshot = Snapshot(tabs=tabs, created_at=now_iso(), source=label)
    save_snapshot(snapshot, paths.tabs_path)

    suffix = ""
    if raw_count != len(tabs):
        suffix = f" ({raw_count - len(tabs)} duplicates merged)"
    print(f"Imported {len(tabs)} tabs from {label}{suffix}")
    print(f"Snapshot: {paths.tabs_path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.data_dir)
    if not paths.tabs_path.is_file():
        print("No snapshot found. Run `tabferry import` first.", file=sys.stderr)
        return 1

    try:
        app = App(paths)
    except (SnapshotError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    httpd = app.server(args.host, args.port)
    port = httpd.server_address[1]
    urls = urls_for(args.host, port)
    print(f"TabFerry {__version__} · {len(app.snapshot.tabs)} tabs · "
          f"{app.state.count()} removed")
    for url in urls:
        print(f"  {url}")
    print("Press Ctrl+C to stop.")
    if args.open and urls:
        webbrowser.open(urls[-1])
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.data_dir)
    try:
        snapshot = load_snapshot(paths.tabs_path)
    except SnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "html":
        state = StateStore(paths.state_path)
        content = render(snapshot, state.removed())
    elif args.format == "json":
        content = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2)
    else:
        content = "\n".join(tab.url for tab in snapshot.tabs) + "\n"

    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"Wrote {target}")
    else:
        sys.stdout.write(content)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.data_dir)
    try:
        snapshot = load_snapshot(paths.tabs_path)
    except SnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    state = StateStore(paths.state_path)
    print(f"Data dir: {paths.data_dir}")
    print(f"Created:  {snapshot.created_at}")
    print(f"Source:   {snapshot.source}")
    print(f"Tabs:     {len(snapshot.tabs)}")
    print(f"Removed:  {state.count()}")
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    for name in sorted(SOURCES):
        print(f"{name:8s} {SOURCES[name].description}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
