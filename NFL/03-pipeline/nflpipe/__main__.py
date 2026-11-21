"""Command dispatcher: ``python -m nflpipe <command> [options]``.

Each command lives in its own module that exposes ``main(argv) -> int``. A module
is imported only when its command is called, so one missing or broken module never
stops the other commands from working (CONTRACTS.md section 7).
"""

import sys

from . import pipeline_version

USAGE = """usage: python -m nflpipe <command> [options]

commands:
  run       ingest, derive, score, check and publish 04-data
            (run --help for options)
  check     verify what is published (read-only)
  resolve   decide whether there is new work (used by GitHub Actions)
  watchdog  fail when the last publish is too old
  export    build the values-only Excel workbook from 04-data
  version   print the pipeline version
"""


def _not_implemented(command: str) -> int:
    """Report a command whose module has not been written yet."""
    print(f"nflpipe {command}: not implemented yet", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Dispatch to the module that owns the command and return its exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0 if argv else 1
    command, rest = argv[0], argv[1:]

    if command == "version":
        print(pipeline_version)
        return 0
    if command == "run":
        from . import run
        return run.main(rest)
    if command == "check":
        try:
            from . import check
        except ImportError:
            return _not_implemented("check")
        return check.main(rest)
    if command == "resolve":
        try:
            from . import resolve
        except ImportError:
            return _not_implemented("resolve")
        return resolve.main(rest)
    if command == "watchdog":
        try:
            from . import watchdog
        except ImportError:
            return _not_implemented("watchdog")
        return watchdog.main(rest)

    if command == "export":
        from . import export_xlsx
        return export_xlsx.main(rest)

    print(f"nflpipe: unknown command '{command}'\n\n{USAGE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
