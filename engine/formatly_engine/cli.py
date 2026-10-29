"""Command line: formatly check / fix / rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import __version__
from .engine import check, fix
from .issues import CATEGORIES
from .rulebook import builtin_names, load_rulebook

MARK = {"pass": "✓", "warn": "!", "fail": "✗"}


def _print_report(report: dict, show: int) -> None:
    c = report["counts"]
    print(f"Rulebook: {report['rulebook']['name']}")
    print(f"Score:    {report['score']}/100")
    print(f"Issues:   {c['errors']} to fix, {c['warnings']} to check, {c['suggestions']} suggestions "
          f"({c['fixable']} auto-fixable)")
    print()
    for cat in report["categories"]:
        print(f"  {MARK[cat['status']]} {cat['name']:<26} {cat['errors']:>3} to fix  {cat['warnings']:>3} to check")
    if show:
        print()
        by_cat: dict[str, list[dict]] = {}
        for i in report["issues"]:
            by_cat.setdefault(i["category"], []).append(i)
        for key, items in by_cat.items():
            print(f"{CATEGORIES.get(key, key)}:")
            for i in items[:show]:
                where = f"[¶{i['block']}] " if i["block"] is not None else ""
                print(f"  - {where}{i['message']}")
            if len(items) > show:
                print(f"  ... and {len(items) - show} more")


def _write_json(path: str | None, data: dict) -> None:
    if path:
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_check(args) -> int:
    result = check(args.document, args.rules)
    if args.output:
        Path(args.output).write_bytes(result.annotated_bytes())
    _write_json(args.json, result.report)
    if not args.quiet:
        _print_report(result.report, args.show)
        if args.output:
            print(f"\nCommented document: {args.output}")
    return 1 if result.report["counts"]["errors"] else 0


def cmd_fix(args) -> int:
    result = fix(args.document, args.rules)
    out = args.output
    if args.annotate:
        Path(out).write_bytes(result.after.annotated_bytes())
    else:
        Path(out).write_bytes(result.fixed)
    _write_json(args.json, {"applied": result.applied, "before": result.before, "after": result.after.report})
    if not args.quiet:
        print(f"Before: {result.before['score']}/100   After: {result.after.report['score']}/100")
        print(f"Fixed {sum(result.applied.values())} issues.\n")
        print("Remaining:")
        _print_report(result.after.report, args.show)
        print(f"\nCorrected document: {out}")
    return 1 if result.after.report["counts"]["errors"] else 0


def cmd_rules(args) -> int:
    if args.action == "list":
        for name in builtin_names():
            print(name)
        return 0
    rb = load_rulebook(args.rulebook)
    if args.action == "show":
        print(yaml.safe_dump(rb.model_dump(mode="json"), sort_keys=False, allow_unicode=True))
    else:
        print(f"OK: {rb.name} (version {rb.version})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="formatly", description="Check and correct documents against a rulebook.")
    p.add_argument("--version", action="version", version=f"formatly {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="check a .docx and optionally write a commented copy")
    c.add_argument("document")
    c.add_argument("-r", "--rules", default="default", help="rulebook file or built-in name (default: default)")
    c.add_argument("-o", "--output", help="write a copy with comments to this .docx")
    c.add_argument("--json", help="write the full report as JSON")
    c.add_argument("--show", type=int, default=5, help="issues to list per category (0 for none)")
    c.add_argument("-q", "--quiet", action="store_true")
    c.set_defaults(func=cmd_check)

    f = sub.add_parser("fix", help="auto-fix a .docx into a new file")
    f.add_argument("document")
    f.add_argument("-r", "--rules", default="default")
    f.add_argument("-o", "--output", required=True, help="where to write the corrected .docx")
    f.add_argument("--annotate", action="store_true", help="also comment on what still needs fixing")
    f.add_argument("--json", help="write before/after reports as JSON")
    f.add_argument("--show", type=int, default=5)
    f.add_argument("-q", "--quiet", action="store_true")
    f.set_defaults(func=cmd_fix)

    r = sub.add_parser("rules", help="list, show or validate rulebooks")
    r.add_argument("action", choices=["list", "show", "validate"])
    r.add_argument("rulebook", nargs="?", default="default")
    r.set_defaults(func=cmd_rules)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"formatly: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
