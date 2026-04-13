from __future__ import annotations

import argparse
import sys

from vwait.features.visual_qa.interfaces.cli.build_index_cli import main as build_index_main
from vwait.features.visual_qa.interfaces.cli.classify_cli import main as classify_main
from vwait.features.visual_qa.interfaces.cli.validate_cli import main as validate_main


def main() -> None:
    parser = argparse.ArgumentParser(description="Convenience entrypoint for Visual QA CLIs.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-index", help="Build FAISS index from reference images")
    sub.add_parser("classify", help="Classify screenshot against existing index")
    sub.add_parser("validate", help="Run full classify + compare + report pipeline")

    args, remaining = parser.parse_known_args()
    sys.argv = [sys.argv[0], *remaining]

    if args.command == "build-index":
        build_index_main()
        return
    if args.command == "classify":
        classify_main()
        return
    if args.command == "validate":
        validate_main()
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
