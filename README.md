# Search My Saves

A personal tool that makes Instagram saved posts searchable by **what you
remember about them**, not by exact caption text or account name.

If you save hundreds of posts across food, travel, fashion, home decor, and
everything else, Instagram's own saved-posts search is close to useless — you
remember *what* something was, not the account, the exact title, or when you
saved it. This project fixes that: type a vague, natural description —
"that quick mango recipe," "restaurants in Tokyo," "black wedding outfit" —
and get the right saved post back, even when those exact words never appeared
in the original caption.

The core idea is **not** "AI categorizes your Instagram posts." It's
**"find what you remember, not what you typed."** A caption like "finally
made this 😍" over a photo of a mango dessert has zero searchable text on its
own — the system still needs to find it from a vague description of what the
food looked like.

## How it works

```
Instagram export (URLs) → Apify → raw post data
        ↓
Supabase: saved_posts (raw, untouched Apify data)
        ↓
AI Processing Worker → Gemini (categorize, extract, describe)
        ↓
Supabase: content_analysis (structured output + embedding)
        ↓
Hybrid Search (keyword + vector, combined via Reciprocal Rank Fusion)
        ↓
Next.js UI
```

Gemini looks at each post's **image/video, not just the caption** — a caption
is frequently just hashtags or "save this!", while the real content only
exists in the media itself. For each post it produces a category, a title, a
one-line summary, and — the most important field — a `search_context`: a
natural-language description of what a person would remember about the post
weeks later, written for retrieval rather than as a caption restatement.

Search combines two retrieval methods in a single Postgres function, fused
with Reciprocal Rank Fusion:
- **Keyword/full-text search** (`tsvector` + GIN index) — catches exact terms.
- **Semantic/vector search** (pgvector + HNSW index) — catches "I don't
  remember the exact words" queries.

## Tech stack

- **Frontend:** Next.js + TypeScript + Tailwind CSS (deployed on Vercel)
- **Backend/database:** Supabase (PostgreSQL + pgvector)
- **Pipeline:** Python (ingestion, AI processing worker, CLI, eval harness)
- **AI:** Gemini API — both for multimodal content understanding and for
  embeddings, so there's a single AI vendor and API key
- **Ingestion:** Apify's Instagram Scraper actor

Everything runs on free tiers — this is a personal, single-user tool, not a
SaaS product. No billing, no multi-tenancy, no Kafka/Redis/Kubernetes.

## Evaluation

Retrieval quality is measured with the same metrics used to evaluate
production search/RAG systems — **recall@k** and **MRR (Mean Reciprocal
Rank)**, the metrics behind benchmarks like MS MARCO and BEIR.

Queries are written **from memory, before looking at what the AI generated**
for those posts — this avoids the common evaluation bug where test queries
unconsciously echo the stored text and inflate the numbers.

On a set of 38 hand-written, blind queries: **recall@5: 94.74% · recall@10:
97.37% · MRR: 0.7671**.

If quality falls short, the fix is applied in a fixed order, cheapest and
highest-leverage first, and never shipped without a measured before/after
number: (1) improve the AI prompt that generates `search_context`, (2) tune
the keyword/semantic weighting in the hybrid search function, (3) add fuzzy
matching for typos, (4) experiment with video frame extraction vs. native
video, and only then (5) query expansion.

## Getting started

### 1. Supabase

Create a free [Supabase](https://supabase.com) project, then apply the
migrations in `supabase/migrations/` in order (via the SQL Editor or the
Supabase CLI). `0004_grants.sql` is required even on a fresh project —
without it, `service_role` has no table access.

### 2. Environment variables

Copy `.env.example` to `.env` at the repo root **and** to `web/.env.local`
(Next.js only reads env files from inside `web/`), and fill in your own
Supabase, Gemini, and Apify credentials.

### 3. Pipeline (Python)

```bash
cd pipeline
python -m venv .venv && source .venv/bin/activate
pip install -e .

python cli.py parse-export path/to/your/instagram_export.json
python cli.py scrape --confirm      # pulls fresh post data via Apify
python cli.py ingest data/apify-raw-<timestamp>.json
python cli.py fetch-media
python cli.py process               # runs Gemini analysis + embeddings
python cli.py search "your vague query here"
```

Run `python cli.py --help` for the full command list (`reprocess`,
`recategorize`, `eval`, and more).

### 4. Web app

```bash
cd web
npm install
npm run dev
```

## License

MIT — see [LICENSE](LICENSE).
