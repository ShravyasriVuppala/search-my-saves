"""Meta export -> normalized PostRef list (plan.md D13/§7.1).

The ONLY module in the pipeline that knows Meta's export format. Everything
downstream consumes plain PostRef objects. Two consumers: apify_client.py
takes the URL list, ingest.py joins saved_at/export_caption back onto the
scraped results by shortcode.

Run standalone:
    cd pipeline && python export_parser.py [path/to/saved_posts.json] [-o output.json]
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from models import PostRef

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "saved_posts.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "post_refs.json"

# Matches Instagram permalinks for posts, reels, and (legacy) IGTV.
SHORTCODE_RE = re.compile(r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")


def fix_mojibake(text: str) -> str:
    """The export's text is UTF-8 that got decoded as latin-1 somewhere in
    Meta's pipeline, so emoji and smart quotes show up mangled (e.g. a mango
    emoji becomes 4 garbage characters). Reversing that recovers the original.
    Text that was never mangled fails one leg of the round-trip and is
    returned unchanged -- real emoji/CJK characters sit outside latin-1's
    0-255 range and raise UnicodeEncodeError immediately; an isolated
    accented character that IS in range typically fails the UTF-8 decode
    instead, since it won't form a valid multi-byte sequence on its own."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _label_map(record: dict) -> dict[str, dict]:
    """label_values is a list of {label, value, href?} dicts, not an object --
    Meta reorders these between export versions, so always match by label,
    never by position."""
    labels: dict[str, dict] = {}
    for entry in record.get("label_values", []):
        label = entry.get("label")
        if label and label not in labels:
            labels[label] = entry
    return labels


def parse_record(record: dict) -> PostRef | None:
    """Returns None for a record with no usable URL/shortcode -- callers
    count and skip these rather than treating them as fatal."""
    labels = _label_map(record)

    url_entry = labels.get("URL")
    if not url_entry:
        return None
    url = url_entry.get("href") or url_entry.get("value")
    if not url:
        return None

    match = SHORTCODE_RE.search(url)
    if not match:
        return None
    shortcode = match.group(1)

    caption = fix_mojibake(labels.get("Caption", {}).get("value", ""))

    timestamp = record.get("timestamp")
    saved_at = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else None

    # collection_name is UNCONFIRMED (plan.md §7.1) -- the per-post record
    # carries only URL + Caption, no collection field. If a full "All time"
    # export turns out to expose collections as sibling files under
    # your_instagram_activity/saved/, wire that lookup in here. Until
    # confirmed, this stays None rather than guessed.
    return PostRef(
        shortcode=shortcode,
        url=url,
        saved_at=saved_at,
        export_caption=caption,
        collection_name=None,
    )


def parse_export(path: Path) -> list[PostRef]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(
            f"{path} is not a JSON list at the top level -- Meta's export format "
            "may have changed. Inspect the file and update parse_record()."
        )

    refs: list[PostRef] = []
    seen: set[str] = set()
    skipped = 0
    duplicates = 0

    for record in raw:
        try:
            ref = parse_record(record)
        except Exception as exc:  # noqa: BLE001 -- one bad record must not abort the run
            print(f"warning: skipping malformed record: {exc}", file=sys.stderr)
            skipped += 1
            continue

        if ref is None:
            skipped += 1
            continue
        if ref.shortcode in seen:
            duplicates += 1
            continue

        seen.add(ref.shortcode)
        refs.append(ref)

    print(
        f"parsed {len(refs)} posts from {len(raw)} records "
        f"({skipped} skipped: no URL/shortcode match, {duplicates} duplicate shortcodes dropped)",
        file=sys.stderr,
    )
    return refs


def _to_json(ref: PostRef) -> dict:
    return {
        "shortcode": ref.shortcode,
        "url": ref.url,
        "saved_at": ref.saved_at.isoformat() if ref.saved_at else None,
        "export_caption": ref.export_caption,
        "collection_name": ref.collection_name,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cli.py parse-export", description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        default=DEFAULT_INPUT,
        type=Path,
        help=f"path to the Meta export's saved_posts.json (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help=f"where to write the normalized PostRef list (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"error: {args.input} does not exist", file=sys.stderr)
        raise SystemExit(1)

    refs = parse_export(args.input)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps([_to_json(r) for r in refs], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {len(refs)} posts to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
