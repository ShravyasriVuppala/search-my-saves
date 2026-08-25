# Search My Saves — Project Brief

## What this is

A personal web application that makes my Instagram saved posts searchable by
what I remember about them, not just by account name or exact caption text.

I save 300+ posts/reels on Instagram across many topics (food, travel, fashion,
home decor, tech, etc.) and Instagram's own saved-posts search is unusable —
I remember *what* something was but not the account, exact title, or when I
saved it.

**The core product is not "AI categorizes Instagram posts."**
**The core product is: "I can find things I saved based on what I remember about them."**

Success looks like typing "mango dessert", "that quick mango recipe",
"restaurants in Tokyo", "black wedding outfit", "home decor with brown
furniture", or "Kafka tutorials" and reliably getting the right saved post back
— even when those exact words never appeared in the original caption.

## Explicitly out of scope

This is a personal project for one user (me), not a SaaS product. Do NOT build:
billing/subscriptions, multi-tenancy, complex auth (a simple password gate is
enough if deployed publicly), Kafka/Redis/Kubernetes/microservices, or
automatic background Instagram syncing. Keep the architecture as simple as the
problem allows.

## Tech stack

- **Frontend:** Next.js + TypeScript + Tailwind CSS, deployed free on Vercel.
  (Not Lovable — its free tier caps at 5 build credits/day and free projects
  are public, which doesn't fit a personal library or ongoing iteration.)
- **Backend/database:** Supabase (PostgreSQL + pgvector), free tier.
- **AI:** Gemini API (free tier) — both for content understanding and for
  embeddings (`text-embedding-004`), so there's a single AI vendor and API key.
- **Ingestion:** Apify Instagram Scraper actor, called from a backend script —
  not from the browser.
- Zero paid infrastructure. Every piece above has a free tier sufficient for
  a single-user, few-thousand-post library.

## Architecture

Keep these four layers logically separate — each replaceable independently:

```
Instagram export (URLs) → Apify → raw post data
        ↓
Supabase: saved_posts (raw, untouched Apify data)
        ↓
AI Processing Worker → Gemini (categorize, extract, describe)
        ↓
Supabase: content_analysis (structured output + embedding)
        ↓
Hybrid Search (keyword + vector, combined)
        ↓
Next.js UI
```

## Data model

### `saved_posts` — raw ingested data, source of truth

```
id                  uuid, primary key
instagram_post_id   text, unique          -- Instagram's shortcode, used for de-dup
instagram_url       text
creator_username    text
caption             text
media_type          text                  -- image | video | carousel
media_url           text                  -- thumbnail/display image URL
posted_at           timestamptz
raw_apify_data      jsonb                 -- full Apify response, kept forever
imported_at         timestamptz default now()
processing_status   text default 'PENDING'  -- PENDING | PROCESSING | COMPLETED | FAILED
processing_error    text                  -- last error message, if FAILED
retry_count         int default 0         -- increment on each failed attempt; cap retries in the worker
created_at          timestamptz default now()
updated_at          timestamptz default now()
```

Never delete or mutate `raw_apify_data` — AI processing must be fully
rerunnable from this table alone, without re-scraping Instagram, in case the
prompt or categorization scheme improves later.

### `content_analysis` — AI-derived data, one row per post

```
post_id           uuid, primary key, references saved_posts(id) on delete cascade
category          text        -- Food | Travel | Fashion | Home | Products | Learning | Entertainment | Ideas | Other
subcategory       text
title             text        -- best short human-readable title
summary           text        -- one-line concise summary
search_context    text        -- 2-4 sentence natural-language description, written the way
                                -- I'd describe the post from memory later — this is the main
                                -- retrieval signal, so it should describe visual content, not
                                -- just restate the caption
keywords          text[]
entities          text[]
ai_metadata       jsonb       -- category-specific fields, schema-less (see below)
embedding         vector(768) -- embedded from title + summary + search_context + keywords combined
ai_model          text        -- which Gemini model produced this, for future comparison
ai_processed_at   timestamptz default now()
```

**Category-specific `ai_metadata` fields** (guidance, not a rigid schema —
only include fields Gemini is actually confident about from the image/caption):
- Food → cuisine, dish_type, ingredients, meal_type, dietary_type, cooking_time
- Travel → country, city, destination, place_type, activity
- Fashion → clothing_type, color, style, occasion, brand
- Home → room, interior_style, furniture, colors, decor_items
- Products → product, brand, product_type, notable_features
- Learning → topic, concepts, technology, learning_type
- Entertainment / Ideas / Other → free-form summary object

## AI content understanding

For each post, Gemini should look at the caption **and** the image/video
thumbnail together — do not rely on caption text alone. A caption like
"finally made this 😍" over a mango dessert photo should still be understood
as a mango dessert. Send available media to the model; design this step so
video-frame extraction can be added later without restructuring anything else.

Gemini should determine, per post: category/subcategory, a useful title, a
concise summary, present entities, descriptive keywords, and — most
importantly — the `search_context`: a natural description of what a person
would remember about this post later, not a restatement of the caption.

## Search

Two retrieval methods, combined:

1. **Keyword/full-text search** — Postgres `tsvector` + `GIN` index over the
   combined text fields. Catches exact terms ("Kafka") reliably.
2. **Semantic/vector search** — pgvector, embedding generated from
   `title + summary + search_context + keywords` joined together (more
   signal than embedding `search_context` alone, especially for sparse posts).
   HNSW index for fast approximate nearest-neighbor lookup.

Combine both via Reciprocal Rank Fusion into a single ranked result list —
implement this as a Postgres function callable via Supabase RPC, not as
separate queries merged in application code. Search should prioritize
relevance over exact word matching: "that quick mango dessert" must be able
to surface a post titled "Mango Yogurt Dessert" even if "quick" and "mango
dessert" never appear together in the source caption.

## Ingestion & incremental sync

Ingestion accepts Apify output and:
1. Normalizes it to the `saved_posts` shape.
2. Checks `instagram_post_id` for duplicates — never reprocess existing posts.
3. Inserts new posts as `PENDING`.
4. AI processing picks up `PENDING` posts asynchronously (a separate
   process/script from ingestion, not inline).
5. On success: stores the structured result + embedding, marks `COMPLETED`.
6. On failure: marks `FAILED`, stores `processing_error`, increments
   `retry_count`. Cap automatic retries (e.g. stop after 3) so a
   permanently-broken post doesn't loop forever — surface it in the UI instead.

Design the ingestion layer so a future incremental sync (compare current
Instagram saves against `instagram_post_id`s already in the database, process
only new ones) is a straightforward addition later. Do not build automatic
Instagram syncing now, and do not implement Instagram credential collection —
ingestion stays export-file-based for now.

## UI

Clean, minimal, personal-tool aesthetic — usability over features.

**Dashboard:** "Search your saves" — large search bar, placeholder "What do
you remember about the post?" — total saved post count, and per-category
counts. Once processing status exists, also show a small breakdown (e.g.
"1,247 total · 1,230 processed · 10 processing · 7 failed").

**Library:** visual grid of saved posts. Each card: thumbnail, title,
category, subcategory, creator, a few tags.

**Post detail:** thumbnail/video, title, AI summary, category, extracted
metadata, keywords, creator, link to the original Instagram post. Don't force
every category into the same layout — show category-specific fields when
present (ingredients for recipes, location for travel, etc.) rather than a
rigid shared template.

**Processing status/retry UI:** (later phase) surface `FAILED` posts with
their error message and a manual retry action.

## Engineering principles

1. Keep ingestion, AI processing, storage, and search as separate, independently replaceable components.
2. Keep raw Apify data (`saved_posts`) completely separate from AI-derived data (`content_analysis`).
3. AI processing must be rerunnable from raw data without re-scraping.
4. Never reprocess a post that's already `COMPLETED`.
5. Category-specific metadata stays in JSONB — don't hardcode a rigid schema per category.
6. No infrastructure beyond what's concretely needed — no Kafka/Redis/K8s/microservices.
7. API keys (Gemini, Apify, Supabase service key) stay server-side only — never in frontend code.
8. Optimize for search quality and the "I remember something vague" experience over UI polish.

## Build order

1. Supabase schema (`saved_posts`, `content_analysis`, indexes, `hybrid_search` function)
2. Ingestion script: Apify output → normalized `saved_posts` rows, dedup by `instagram_post_id`
3. AI processing worker: Gemini categorization/extraction/search_context + embedding generation, with retry-aware status handling
4. Hybrid search (keyword + vector via RRF) — verify from a script/SQL editor before building UI
5. Next.js dashboard, library grid, and post detail page, calling Supabase directly
6. Processing status/retry UI, category filters, browsing

Build and verify each phase before moving to the next — phase 4 (search
returning good results from the CLI/SQL editor) should work before any UI
code is written.

## Success criteria

I can take my existing 300+ Instagram saved posts, run them through this
pipeline, and reliably find the post I'm thinking of by typing a vague,
natural description of it — not the exact caption, not the account name,
just what I remember.
