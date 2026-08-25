"""CLI search: embed the query, call hybrid_search via RPC, print results
(plan.md §9). This is also what eval/run_eval.py calls to score retrieval
quality -- one implementation of "search" for both the human and the eval.
"""

import argparse
import sys

from config import Settings, load_settings
from db import get_client
from gemini.embed import embed_query


def search(
    settings: Settings, query: str, limit: int = 10, category: str | None = None
) -> list[dict]:
    client = get_client(settings)
    embedding = embed_query(settings, query)

    result = client.rpc(
        "hybrid_search",
        {
            "query_text": query,
            "query_embedding": embedding,
            "match_count": limit,
            "filter_category": category,
        },
    ).execute()
    return result.data or []


def print_results(query: str, limit: int = 10, category: str | None = None) -> None:
    settings = load_settings()
    results = search(settings, query, limit=limit, category=category)

    if not results:
        print("no results.")
        return

    for i, row in enumerate(results, 1):
        score = row.get("score")
        score_str = f"{score:.4f}" if score is not None else "?"
        print(f"{i}. {row.get('title') or '(untitled)'}  [{row.get('category')}]")
        print(
            f"   score={score_str}  fts_rank={row.get('fts_rank')}  "
            f"semantic_rank={row.get('semantic_rank')}"
        )
        print(f"   by @{row.get('creator_username')}  {row.get('instagram_url')}")
        if row.get("summary"):
            print(f"   {row['summary']}")
        print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cli.py search", description=__doc__)
    parser.add_argument("query")
    parser.add_argument("-n", "--limit", type=int, default=10)
    parser.add_argument("--category", default=None)
    args = parser.parse_args(argv)
    print_results(args.query, limit=args.limit, category=args.category)


if __name__ == "__main__":
    main(sys.argv[1:])
