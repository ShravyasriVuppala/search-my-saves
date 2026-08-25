"""recall@k / MRR retrieval eval (plan.md §9.1, D11).

No retrieval change (prompt edit, RRF weight tuning, rrf_k) ships without a
before/after number from this. Reads eval/queries.json -- a list of
{"query": "...", "expect_shortcode": "..."} pairs written from memory,
BEFORE looking at the database, so the eval measures real recall instead of
queries reverse-engineered from what's already there.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# eval/ is a sibling of pipeline/, not inside it -- this is the one place
# that needs an explicit sys.path fix-up to reach the pipeline's modules.
sys.path.insert(0, str(REPO_ROOT / "pipeline"))

from config import load_settings  # noqa: E402
from export_parser import SHORTCODE_RE  # noqa: E402
from search import search  # noqa: E402

DEFAULT_QUERIES = REPO_ROOT / "eval" / "queries.json"
DEFAULT_K_VALUES = (5, 10)


def _shortcode_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = SHORTCODE_RE.search(url)
    return match.group(1) if match else None


def evaluate(queries: list[dict], k_values: tuple[int, ...] = DEFAULT_K_VALUES) -> dict:
    settings = load_settings()
    max_k = max(k_values)

    hits_at_k = dict.fromkeys(k_values, 0)
    reciprocal_ranks: list[float] = []
    missed: list[str] = []
    scored = 0

    for entry in queries:
        try:
            query_text = entry["query"]
            expected = entry["expect_shortcode"]
        except KeyError as exc:
            print(f"warning: skipping malformed entry (missing {exc}): {entry}", file=sys.stderr)
            continue
        scored += 1

        results = search(settings, query_text, limit=max_k)
        shortcodes = [_shortcode_from_url(r.get("instagram_url")) for r in results]

        rank = next((i for i, sc in enumerate(shortcodes, 1) if sc == expected), None)

        for k in k_values:
            if rank is not None and rank <= k:
                hits_at_k[k] += 1

        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        if rank is None:
            missed.append(f"{query_text!r} -> expected {expected}, not in top {max_k}")

    # denominator is queries actually scored, not len(queries) -- a
    # malformed entry that got skipped above must not silently drag down
    # every recall percentage.
    report: dict = {f"recall@{k}": (hits_at_k[k] / scored if scored else 0.0) for k in k_values}
    report["mrr"] = sum(reciprocal_ranks) / scored if scored else 0.0
    report["missed"] = missed
    report["n"] = scored
    return report


def main(queries_path: Path | None = None) -> None:
    path = queries_path or DEFAULT_QUERIES

    queries = []
    if path.exists():
        try:
            queries = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"error: {path} is not valid JSON: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    if not queries:
        print(
            f"error: {path} has no queries yet. Write ~25 vague, realistic queries "
            "from memory -- BEFORE looking at the database -- as "
            '[{"query": "that quick mango dessert", "expect_shortcode": "Cabc123"}, ...] '
            "(plan.md §9.1). Get the shortcode from a post's Instagram URL.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    report = evaluate(queries)

    print(f"n={report['n']} queries")
    for k in DEFAULT_K_VALUES:
        print(f"recall@{k}: {report[f'recall@{k}']:.2%}")
    print(f"MRR: {report['mrr']:.4f}")
    if report["missed"]:
        print("\nmissed:")
        for line in report["missed"]:
            print(f"  - {line}")


if __name__ == "__main__":
    main()
