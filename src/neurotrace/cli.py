"""`neurotrace` command-line entry point.

Two subcommands, both reading from a SQLiteStorage db: `list` (which traces
are in this file) and `view` (render one). `view` defaults to the most
recently started trace so `neurotrace view traces.db` works right after a
run without having to look up a trace_id first.
"""

from __future__ import annotations

import argparse
import sys

from neurotrace.core.storage import SQLiteStorage
from neurotrace.viewer.render import render_trace


def _cmd_list(args: argparse.Namespace) -> int:
    storage = SQLiteStorage(args.db_path)
    try:
        traces = storage.list_traces()
        if not traces:
            print("(no traces)")
            return 0
        for trace in traces:
            status = trace.ended_at.isoformat() if trace.ended_at else "in progress"
            print(f"{trace.trace_id}  {trace.name}  {trace.started_at.isoformat()}  [{status}]")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
