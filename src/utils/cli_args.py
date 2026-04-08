from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field


@dataclass
class StartupArgs:
    settings_path: str | None = None
    open_paths: list[str] = field(default_factory=list)
    passthrough_args: list[str] = field(default_factory=list)


def parse_startup_args(argv: list[str] | None = None) -> StartupArgs:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--settings")
    parser.add_argument("--open", nargs="+", action="append", default=[])

    known_args, passthrough_args = parser.parse_known_args(argv)

    open_paths: list[str] = []
    for open_group in known_args.open:
        for path in open_group:
            open_paths.append(os.path.abspath(path))

    settings_path = (
        os.path.abspath(known_args.settings)
        if known_args.settings
        else None
    )

    return StartupArgs(
        settings_path=settings_path,
        open_paths=open_paths,
        passthrough_args=passthrough_args,
    )
