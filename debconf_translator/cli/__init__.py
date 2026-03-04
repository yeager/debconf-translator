"""CLI interface for debconf-translator."""

import argparse
import sys

from .. import __version__, _



def main():
    parser = argparse.ArgumentParser(
        prog="debconf-translator",
        description=_("Debconf Translation Manager — manage debconf template translations"),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # GUI
    sub.add_parser("gui", help=_("Launch the graphical interface"))

    # Status
    status_p = sub.add_parser("status", help=_("Show translation status for a language"))
    status_p.add_argument("lang", default="sv", nargs="?", help=_("Language code (default: sv)"))
    status_p.add_argument("--json", "-j", action="store_true", help=_("Output as JSON"))
    status_p.add_argument("-q", "--quiet", action="store_true", help=_("Minimal output"))

    # Fetch
    fetch_p = sub.add_parser("fetch", help=_("Download POT files for untranslated packages"))
    fetch_p.add_argument("lang", default="sv", nargs="?")
    fetch_p.add_argument("--output", "-o", default=".", help=_("Output directory"))

    # Reviews
    reviews_p = sub.add_parser("reviews", help=_("Show packages under review"))
    reviews_p.add_argument("--json", "-j", action="store_true", help=_("Output as JSON"))

    args = parser.parse_args()

    if args.command is None or args.command == "gui":
        from ..app import main as gui_main
        return gui_main()

    if args.command == "status":
        return _cmd_status(args)
    elif args.command == "fetch":
        return _cmd_fetch(args)
    elif args.command == "reviews":
        return _cmd_reviews(args)


def _cmd_status(args):
    from ..scraper import fetch_language_status
    stats, packages, translators = fetch_language_status(args.lang)

    if args.json:
        import json
        print(json.dumps({
            "language": stats.code,
            "translated": stats.translated,
            "total": stats.total,
            "progress": round(stats.progress, 1),
            "untranslated_packages": len(packages),
            "packages": [{"name": p.name, "strings": p.strings_total} for p in packages],
        }, indent=2))
    elif args.quiet:
        print(f"{stats.translated}/{stats.total} ({stats.progress:.1f}%)")
    else:
        print(f"Language: {args.lang}")
        print(f"Translated: {stats.translated}/{stats.total} ({stats.progress:.1f}%)")
        print(f"Untranslated packages: {len(packages)}")
        if packages:
            print()
            packages.sort(key=lambda p: p.strings_total, reverse=True)
            for p in packages[:20]:
                print(f"  {p.name:40s} {p.strings_total:4d} strings")
            if len(packages) > 20:
                print(f"  ... and {len(packages) - 20} more")

        if translators:
            medals = ["🥇", "🥈", "🥉"]
            print(f"\nTop translators ({args.lang}):")
            for i, t in enumerate(translators[:10]):
                medal = medals[i] if i < 3 else f"  #{i+1}"
                print(f"  {medal} {t.name:35s} {t.strings:5d} strings ({t.packages} pkgs)")


def _cmd_fetch(args):
    from ..scraper import fetch_language_status, fetch_pot_file
    from pathlib import Path

    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    _, packages, _ = fetch_language_status(args.lang)
    print(f"Found {len(packages)} untranslated packages")

    for pkg in packages:
        pot = fetch_pot_file(pkg.name)
        if pot:
            (outdir / f"{pkg.name}.pot").write_text(pot)
            print(f"  ✓ {pkg.name}")
        else:
            print(f"  ✗ {pkg.name} (not found)")


def _cmd_reviews(args):
    from ..scraper import fetch_reviews
    reviews = fetch_reviews()

    if not reviews:
        print("No active reviews found")
        return

    if args.json:
        import json
        print(json.dumps([{
            "package": r.package,
            "status": r.status,
            "bug": r.bug_number,
        } for r in reviews], indent=2))
    else:
        print(f"{len(reviews)} packages under review:")
        for r in reviews:
            bug = f" (#{r.bug_number})" if r.bug_number else ""
            print(f"  {r.package:40s} {r.status:10s}{bug}")
