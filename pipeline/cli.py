"""Unified CLI for the pipeline (plan.md §5).

Run from pipeline/, with the venv active:
    python cli.py parse-export [input] [-o output]
    python cli.py scrape [--refs path] [--confirm]
    python cli.py ingest <raw.json> [--refs path]
    python cli.py fetch-media
    python cli.py process [--cap N]
    python cli.py search "<query>" [-n 10] [--category Food]
    python cli.py eval

Each subcommand supports --help for its own options.
"""

import argparse
import sys
from pathlib import Path

import apify_client
import export_parser
import ingest as ingest_module
import media
import search as search_module
import worker

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))


def _cmd_fetch_media(argv: list[str]) -> None:
    if argv:
        print("fetch-media takes no arguments", file=sys.stderr)
        raise SystemExit(2)
    media.fetch_all_pending_thumbnails()


def _cmd_process(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="cli.py process")
    parser.add_argument(
        "--cap", type=int, default=None, help="override WORKER_DAILY_CAP for this run"
    )
    args = parser.parse_args(argv)
    worker.run(daily_cap=args.cap)


def _cmd_eval(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="cli.py eval")
    parser.add_argument(
        "--queries", type=Path, default=None, help="path to queries.json (default: eval/queries.json)"
    )
    args = parser.parse_args(argv)

    import run_eval  # imported lazily -- sys.path needs eval/ on it first, done above

    run_eval.main(queries_path=args.queries)


COMMANDS = {
    "parse-export": export_parser.main,
    "scrape": apify_client.main,
    "ingest": ingest_module.main,
    "fetch-media": _cmd_fetch_media,
    "process": _cmd_process,
    "search": search_module.main,
    "eval": _cmd_eval,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print(f"commands: {', '.join(COMMANDS)}")
        return

    command = sys.argv[1]
    if command not in COMMANDS:
        print(f"unknown command {command!r}. commands: {', '.join(COMMANDS)}", file=sys.stderr)
        raise SystemExit(2)

    COMMANDS[command](sys.argv[2:])


if __name__ == "__main__":
    main()
