"""`neurotrace` command-line entry point.

Three subcommands over a SQLiteStorage db: `list` (which traces are in this
file), `view` (render one as text), and `serve` (expose them as JSON over
HTTP). `view` defaults to the most recently started trace so
`neurotrace view traces.db` works right after a run without having to look up
a trace_id first.
"""

from __future__ import annotations

import argparse
import sys

from neurotrace.core.storage import SQLiteStorage
from neurotrace.viewer.render import render_trace
from neurotrace.viewer.server import DEFAULT_HOST, DEFAULT_PORT


def _cmd_list(args: argparse.Namespace) -> int:
    storage = SQLiteStorage(args.db_path)
    try:
        summaries = storage.list_trace_summaries()
        if not summaries:
            print("(no traces)")
            return 0
        for summary in summaries:
            status = summary.ended_at.isoformat() if summary.ended_at else "in progress"
            counts = f"{summary.event_count} events"
            if summary.error_count:
                counts += f", {summary.error_count} errored"
            print(
                f"{summary.trace_id}  {summary.name}  {summary.started_at.isoformat()}  "
                f"[{status}]  ({counts})"
            )
        return 0
    finally:
        storage.close()


def _cmd_view(args: argparse.Namespace) -> int:
    storage = SQLiteStorage(args.db_path)
    try:
        if args.trace_id:
            trace = storage.get_trace(args.trace_id)
            if trace is None:
                print(f"no trace with id {args.trace_id!r} in {args.db_path}", file=sys.stderr)
                return 1
        else:
            traces = storage.list_traces()
            if not traces:
                print(f"no traces in {args.db_path}", file=sys.stderr)
                return 1
            trace = traces[-1]

        print(render_trace(trace))
        return 0
    finally:
        storage.close()


def _cmd_serve(args: argparse.Namespace) -> int:
    # Imported here, not at module scope: `list` and `view` are the common
    # commands and shouldn't pay for pulling in FastAPI and uvicorn.
    from neurotrace.viewer.server import create_app

    try:
        app = create_app(args.db_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    import uvicorn

    print(f"serving {args.db_path} on http://{args.host}:{args.port}  (ctrl-c to stop)")
    print(f"  traces:  http://{args.host}:{args.port}/api/traces")
    print(f"  docs:    http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neurotrace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list traces stored in a db")
    list_parser.add_argument("db_path")
    list_parser.set_defaults(func=_cmd_list)

    view_parser = subparsers.add_parser("view", help="render a trace as a timeline")
    view_parser.add_argument("db_path")
    view_parser.add_argument(
        "--trace-id",
        default=None,
        help="trace to render; defaults to the most recently started trace",
    )
    view_parser.set_defaults(func=_cmd_view)

    serve_parser = subparsers.add_parser("serve", help="serve traces as JSON over HTTP")
    serve_parser.add_argument("db_path")
    serve_parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"interface to bind; defaults to {DEFAULT_HOST} (loopback only)",
    )
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
