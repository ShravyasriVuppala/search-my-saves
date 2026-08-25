# Search My Saves — Implementation Plan

> Companion to `CLAUDE.md`. `CLAUDE.md` is the **product brief** (what and why).
> This file is the **build plan** (how, in what order, with what exact contracts).
> Deltas from the brief are listed in §2 with reasons; everything else in
> `CLAUDE.md` stands unchanged.
>
> Last updated 2026-08-24. A model picking this up should read `CLAUDE.md`, then
> this file, then §11 `Phase status` to see where to start.

---

## 1. One-paragraph restatement

Single-user web app. I feed in my Instagram saved-post URLs, a pipeline scrapes
them (Apify), understands each one with Gemini (**media + caption together**),
stores a structured record plus a 768-dim embedding in Supabase/pgvector, and a
Next.js UI lets me find any of them by typing a vague memory
("that quick mango dessert"). Zero paid infrastructure. Search quality is the
product; UI polish is not.

---

## 2. Prior art: `~/Documents/RecipeSystem` (reference only — do not extend)

A previous **trial spike** built a narrow vertical of this: Meta export → Apify
→ cv2 frame extraction → `gemini-3.1-flash-lite` → Airtable, for recipes only.

**It is a throwaway prototype. Do not build on it, import from it, or copy its
structure.** Everything in this project is written fresh and properly. Its only
value is that it *empirically validated* the following, which this plan now
treats as known rather than assumed:

| Validated | Detail |
|---|---|
| Apify returns usable video | `videoUrl`, `videoDuration`, `type: "Video"`, `productType: "clips"` are all present and the CDN link downloads with a browser `User-Agent` |
| Frame extraction → Gemini works | 12 frames downscaled to 480×854, passed as JPEG parts, produced good structured extraction |
| `gemini-3.1-flash-lite` is a good fit | Handles multi-frame + caption, honours `response_mime_type="application/json"` |
| Real Meta export shape | §7.1 — flat list with `label_values`, **not** the `saved_saved_media`/`string_map_data` shape assumed by most docs |
| Export already contains captions | Caption-only analysis is possible with no Apify call at all |
| Export text is double-encoded | Mojibake; needs a fixup pass (§7.1) |

**Known defects in the spike that this build must not reproduce:**

1. **Media analysis was gated on `len(caption) < 40`.** In its own 7-post sample,
   caption lengths were `[423, 688, 1088, 791, 26, 851, 1955]` — six of seven
   posts were never looked at visually. Caption *length* is not caption
   *informativeness*: the 1955-char caption was mostly hashtag spam. **Here,
   media is always analyzed** (§8.5).
2. No `response_schema` — the JSON shape lived only in prompt prose.
3. No persistence of raw scrape data, no dedup, no status/retry model.
4. Broken bookkeeping (`skipped_posts.json` was byte-identical to the input;
   `temp.py` was a byte-identical copy of `bulkextractor.py`).
5. Airtable as the store → no embeddings, no vector search, no semantic recall.

**Scale reality check:** the spike ran on 7 posts. The current Meta export
contains **85 saved posts**. Quota math below is therefore comfortable, but has
not been exercised at volume.

---

## 3. Deltas from `CLAUDE.md`

| # | `CLAUDE.md` says | Change to | Why |
|---|---|---|---|
| D1 | Embeddings via `text-embedding-004` | `gemini-embedding-001`, `output_dimensionality: 768` | `text-embedding-004` was **deprecated Jan 2026**. MRL truncation to 768 costs ~0.26% quality vs 3072, so `vector(768)` and the schema stand. |
| D2 | (not mentioned) | Asymmetric `task_type`: `RETRIEVAL_DOCUMENT` for posts, `RETRIEVAL_QUERY` for queries | Free, one parameter, measurably better retrieval. Both sides must use the same model + dims. |
| D3 | (not mentioned) | **L2-normalize** truncated embeddings before storing | MRL-truncated `gemini-embedding-001` output isn't guaranteed unit-length; pgvector cosine misbehaves subtly otherwise. |
| D4 | Store `media_url` and render it | **Download the thumbnail once at ingest to Supabase Storage**; keep the original URL too | Instagram CDN URLs are signed and **expire in days-to-weeks**. Without this the library grid 404s a month after ingest. |
| D5 | UI calls "Supabase directly" | All DB access **server-side**; browser never talks to Supabase | Direct browser access needs anon key + RLS + real auth. Server-side is simpler *and* satisfies principle 7. |
| D6 | (not mentioned) | Weekly keep-alive ping | **Supabase free projects pause after 7 days idle.** A sporadically-used personal tool will hit this. |
| D7 | (not mentioned) | GitHub Actions for keep-alive + manual pipeline runs | Free, reproducible. Vercel Hobby cron is once-per-day with hour jitter. |
| D8 | (not mentioned) | Gemini **structured output** (`response_mime_type` + `response_schema`) | Removes all JSON-repair code. The spike used prompt-prose schema (§2 defect 2). |
| D9 | (not mentioned) | Add `prompt_version` | The brief requires rerunnability when the prompt improves — without a version stamp you can't tell which rows are stale. |
| D10 | (not mentioned) | Add `saved_at` (confirmed present) and `collection_name` (**unconfirmed** — see §7.1) | "the thing I saved last month" is a real memory cue, and `saved_at` exists only in the export — Apify knows when the creator *posted*, never when *I saved*. So it's free to capture now and unrecoverable later. `collection_name` is speculative: the per-post export records have no collection field. Verify against the full export; drop the column if it isn't there. |
| D11 | (not mentioned) | **Eval harness**: `eval/queries.json`, recall@5 / MRR | The success criterion is a retrieval-quality claim. Without measurement you tune by vibes. Highest-leverage addition here. |
| D12 | (not mentioned) | Denormalize `source_text` into `content_analysis`; `tsvector` as a generated column | Generated columns can't cross tables; this keeps FTS single-table, weighted, always in sync. |
| D13 | Next.js + TypeScript | **Python pipeline + TypeScript Next.js UI**, DB schema as the contract | Python is the right tool for the scrape/frame/LLM half and matches the existing venv + PyCharm setup; TS is right for Next.js. One shared `schema/analysis_schema.json` keeps the Gemini output shape honest across both. |
| D14 | (not mentioned) | Analysis model `gemini-3.1-flash-lite` | 1,500 RPD / 30 RPM free vs ~250 RPD / 10 RPM on 2.5 Flash, higher Intelligence Index (34 vs 21), faster, and validated by the spike. Caveat: **preview model** — keep it in env, stamp `ai_model` per row. |
| D15 | Video-frame extraction is a "later" addition | **Media is always analyzed, in Phase 3, never gated on caption length** (§8.5) | A reel's cover frame is often a talking head or title card while the content is on-screen text and narration. This is the product's core failure mode, not a nice-to-have. |

**Unchanged, deliberately:** four-layer separation, raw-vs-derived split,
RRF-in-Postgres, category-specific JSONB, build order, no Kafka/Redis/K8s.

---

## 4. Free-tier budget (verified Aug 2026)

| Service | Free allowance | Needed | Headroom |
|---|---|---|---|
| **Apify** | $5 credit/month, no card | `apify/instagram-scraper` at **$1.50/1,000 posts** → 85 posts ≈ **$0.13** one-time | ~35× per month |
| **Gemini** | `gemini-3.1-flash-lite`: **1,500 RPD / 30 RPM / 250K TPM**; embeddings ~100 RPM | ~85 analysis + ~85 embed calls, one-time; then a few query embeds/day | Trivially fits — one run, minutes |
| **Supabase** | 500 MB DB, 1 GB storage, 5 GB egress, 2 projects | 85 posts ≈ 3 MB jsonb + <1 MB vectors + ~10 MB thumbnails | Fits ~10,000 posts. **Pauses after 7 days idle → D6** |
| **Vercel** | Hobby, non-commercial | 1 personal server-rendered app | Fine. No ads/payments, ever |
| **GitHub Actions** | 2,000 min/mo (private repo) | keep-alive + occasional runs | Fine. Scheduled workflows auto-disable after 60 days repo inactivity |

**Recurring cost: $0.** Hard rules: no Supabase Pro, no payment method on Apify,
never exceed the $5 monthly credit — wait for reset instead.

---

## 5. Repo layout

```
SearchMySaves/
├─ CLAUDE.md                    # product brief
├─ plan.md                      # this file
├─ .env                         # gitignored — all secrets
├─ .env.example                 # committed
├─ .gitignore
│
├─ supabase/migrations/
│  ├─ 0001_schema.sql
│  ├─ 0002_indexes.sql
│  └─ 0003_hybrid_search.sql
│
├─ schema/
│  └─ analysis_schema.json      # D13: single source of truth for Gemini output
│                               #      → Python response_schema AND TS types
│
├─ pipeline/                    # Python. `uv`/venv, ruff, typed with dataclasses
│  ├─ pyproject.toml
│  ├─ config.py                 # env loading, validated at import
│  ├─ db.py                     # supabase client (service role)
│  ├─ models.py                 # SavedPost / AnalysisResult dataclasses
│  ├─ export_parser.py          # §7.1 Meta export → PostRef[]
│  ├─ apify_client.py           # §7.2
│  ├─ ingest.py                 # §7.3 normalize + dedup → saved_posts
│  ├─ media.py                  # §7.4 thumbnails → Storage; §8.5 frame extraction
│  ├─ gemini/
│  │  ├─ client.py
│  │  ├─ prompt.py              # ANALYSIS_PROMPT + PROMPT_VERSION
│  │  ├─ analyze.py             # media + caption → AnalysisResult
│  │  └─ embed.py               # embed_document / embed_query, normalizes
│  ├─ worker.py                 # §8 PENDING → COMPLETED/FAILED
│  └─ cli.py                    # `python -m pipeline.cli <command>`
│
├─ eval/
│  ├─ queries.json              # [{ "query": "...", "expect_shortcode": "..." }]
│  └─ run_eval.py               # recall@5 / recall@10 / MRR
│
├─ data/                        # gitignored — export, apify json, backups
│
├─ web/                         # Next.js + TS + Tailwind
│  ├─ middleware.ts             # password-cookie gate
│  ├─ lib/{supabase,search,types}.ts
│  ├─ app/page.tsx              # dashboard + search
│  ├─ app/library/page.tsx
│  ├─ app/post/[id]/page.tsx
│  ├─ app/status/page.tsx       # phase 6
│  └─ app/api/{search,retry,keepalive}/route.ts
│
└─ .github/workflows/{keepalive,pipeline}.yml
```

CLI surface: `python -m pipeline.cli parse-export | scrape | ingest | fetch-media
| process | search "<q>" | reprocess | eval`.

---

## 6. Environment variables

```bash
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...        # SERVER ONLY. never NEXT_PUBLIC_*
SUPABASE_STORAGE_BUCKET=thumbnails

# Gemini
GEMINI_API_KEY=AIza...
GEMINI_ANALYSIS_MODEL=gemini-3.1-flash-lite    # D14 — preview; swap here if it breaks
GEMINI_ANALYSIS_FALLBACK_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIM=768

# Apify (pipeline only, never deployed)
APIFY_TOKEN=apify_api_...

# App auth
APP_PASSWORD=<long random>
APP_SESSION_SECRET=<long random>

# Worker / media
WORKER_RPM=10                # under the 30 RPM ceiling; frames are token-heavy
WORKER_DAILY_CAP=400         # safety net under 1,500 RPD
WORKER_MAX_RETRIES=3
MEDIA_MAX_FRAMES=12          # validated by the spike
MEDIA_FRAME_WIDTH=480
MEDIA_FRAME_HEIGHT=854
VIDEO_MAX_MB=25              # above this, fall back to thumbnail
```

Never prefix any of these `NEXT_PUBLIC_`. The browser needs zero secrets (D5).

---

## 7. Phase 2 — Ingestion

### 7.1 `export_parser.py` — Meta export → post refs

**The real format** (confirmed against an actual export — a flat JSON list, not
the `saved_saved_media`/`string_map_data` shape most docs describe):

```json
[
  { "timestamp": 1785565921,
    "media": [],
    "label_values": [
      { "label": "URL",     "value": "https://www.instagram.com/reel/DbdJ2NYMK9O/",
                            "href":  "https://www.instagram.com/reel/DbdJ2NYMK9O/" },
      { "label": "Caption", "value": "Chocolate Mochi Balls with a fluffy sea salt cream dip..." }
    ] }
]
```

Parser requirements:
- Walk `label_values`, match on `label`, don't rely on positional index.
- Extract shortcode via regex `instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)`.
- `timestamp` → `saved_at` (epoch seconds, UTC).
- **Fix the mojibake.** Export text is UTF-8 bytes decoded as latin-1
  (`ð«` is 🍫). Apply
  `s.encode('latin-1').decode('utf-8')` with a try/except fallback to the raw
  string. Without this, every emoji and smart quote is corrupted **in the
  embeddings**, which silently degrades retrieval.
- Keep the export caption as `export_caption` — it's a free fallback if Apify
  ever fails on a post, or if the $5 credit runs out mid-run.
- Still walk defensively: Meta changes key names between export versions.
- **`collection_name` is UNCONFIRMED.** The per-post records carry only
  `timestamp` + `label_values` (URL, Caption) — there is no collection field.
  Instagram stores collection membership in *separate* files in the export
  archive. When the full "All time" export lands, check the
  `your_instagram_activity/saved/` folder for sibling files (e.g. one JSON per
  collection) and populate `collection_name` from the filename if so.
  **If it isn't there, drop the column** rather than carrying a
  permanently-null field. Do not block ingestion on this.

Output `data/post_refs.json`, deduped by shortcode. **Acceptance:** count ≈ 85
on the current partial export (see §4 — a full "All time" export should be
~300+; a ~12-month range means the export was date-limited and should be
re-requested).

**Architectural note:** this is the *only* module in the system that knows
Meta's export format exists — everything downstream consumes normalized
`PostRef` objects. It has two consumers: `apify_client.py` takes the URL list,
and `ingest.py` joins `saved_at` / `export_caption` back onto scraped results by
shortcode. The shortcode derived here is the system-wide join key (dedup in
`saved_posts`, the link to `content_analysis`, and the reference used by
`eval/queries.json`), so it is derived exactly once, here.

### 7.2 `apify_client.py`

- Actor `apify/instagram-scraper`, input
  `{ directUrls: [...], resultsType: "posts", resultsLimit: 1, addParentData: false }`.
- **Cost control:** print post count and estimate (`n/1000 × $1.50`), require an
  explicit `--confirm` flag, and skip shortcodes already in `saved_posts` so
  re-runs cost nothing.
- **Write the raw response to `data/apify-raw-<ts>.json` before anything else
  touches it** — this is the disaster-recovery copy; losing it means paying to
  re-scrape.
- Batch ~50 URLs; keep completed batches on partial failure.

### 7.3 `ingest.py` — raw → `saved_posts`

| column | source |
|---|---|
| `instagram_post_id` | `shortCode` |
| `instagram_url` | `url` |
| `creator_username` | `ownerUsername` |
| `caption` | `caption`, falling back to `export_caption` |
| `media_type` | `type`: `Image`→`image`, `Video`→`video`, `Sidecar`→`carousel` |
| `product_type` | `productType` (`clips` = reel) |
| `media_url` | `displayUrl` (carousel: `childPosts[0].displayUrl`) |
| `video_url` | `videoUrl` (expires — used only inside the processing window) |
| `video_duration` | `videoDuration` |
| `alt_text` | `alt` — Instagram's own accessibility description, a free extra signal |
| `posted_at` | `timestamp` |
| `saved_at`, `export_caption` | joined from `data/post_refs.json` by shortcode |
| `collection_name` | same join **if** §7.1 confirms it exists in the full export; otherwise leave null and drop the column |
| `raw_apify_data` | the entire item, untouched |

Upsert `on_conflict=instagram_post_id, ignore_duplicates=True` — **never**
overwrite an existing row (principle 4). New rows land `PENDING`.

**Acceptance:** row count == unique shortcodes; re-running inserts 0 and mutates
nothing.

### 7.4 `media.py` — thumbnails → Supabase Storage (D4)

For each row with `media_url` and no `media_storage_path`: fetch (browser
`User-Agent` required — validated), downscale to ~800px longest edge / JPEG q80,
upload to the **private** `thumbnails` bucket as `<instagram_post_id>.jpg`,
store the path. On failure leave null and continue.

**Run within days of scraping** — the CDN URLs are already expiring.

---

## 8. Phase 3 — AI processing worker

### 8.1 Loop

```
1. reset rows stuck in PROCESSING > 30 min → PENDING
2. claim batch: PENDING and retry_count < WORKER_MAX_RETRIES, order by saved_at desc
3. mark PROCESSING (so a second run can't double-spend quota)
4. per post, throttled to WORKER_RPM:
     a. resolve media per the ladder in §8.5
     b. Gemini analysis (structured output) → AnalysisResult
     c. build embedding_input → embed (RETRIEVAL_DOCUMENT) → L2-normalize
     d. upsert content_analysis (incl. source_text, analysis_input_mode)
     e. mark COMPLETED
   on error: FAILED + processing_error + retry_count += 1
5. stop at WORKER_DAILY_CAP; print a resumable summary
```

Non-negotiable: never touch a `COMPLETED` post (principle 4); safe to kill and
restart; 429/503 → exponential backoff with jitter and **do not** increment
`retry_count` (quota isn't the post's fault) — schema/content errors do count.

### 8.2 Analysis call

Model `GEMINI_ANALYSIS_MODEL` (`gemini-3.1-flash-lite`). Media parts + caption
in one multimodal request, `response_mime_type="application/json"` **plus a real
`response_schema`** (D8) generated from `schema/analysis_schema.json`:

```jsonc
{ "category":       { "enum": ["Food","Travel","Fashion","Home","Products",
                               "Learning","Entertainment","Ideas","Other"] },
  "subcategory":    "string",
  "title":          "string",
  "summary":        "string",
  "search_context": "string",
  "keywords":       ["string"],
  "entities":       ["string"],
  "ai_metadata":    "object"   // free-form, category-specific
}
// required: category, title, summary, search_context, keywords
```

`temperature: 0.2` (validated).

### 8.3 Prompt (this is the product — iterate here, version it)

`PROMPT_VERSION = "v1"`; bump on every meaningful edit.

Must contain:
- *You are indexing one Instagram post for a personal search engine. The user
  saved it and will later try to find it by describing it vaguely from memory.*
- **Look at the media first, then the caption.** The media is the more reliable
  signal. "finally made this 😍" over a mango dessert is a **mango dessert** post.
- **Read on-screen text overlays, labels, and step captions in the frames** —
  in reels this is often the only place the real content appears.
- `search_context` (most important): 2–4 sentences describing what a person
  would remember weeks later. Describe **visible content** — colors,
  ingredients, setting, garment type, room, place, on-screen text. **Do not
  restate the caption.** Never mention Instagram, the creator, or engagement.
  Naturally include everyday search words ("quick", "weeknight", "date-night")
  where they genuinely apply.
- `title`: ≤8 words, specific ("Mango Yogurt Dessert", not "Recipe").
- `keywords`: 8–15 lowercase terms **including synonyms and phrasings absent
  from the caption**. This is what rescues exact-term search.
- `entities`: proper nouns actually visible/named. Empty if none. **Never guess
  a location or brand.**
- `ai_metadata`: only fields you're confident about, per the category guidance in
  `CLAUDE.md`. Omit uncertain fields rather than guessing or nulling.
- Ignore hashtag blocks and engagement-bait ("save this!", "follow for more") —
  they carry no retrieval signal.

Include 2–3 few-shot examples (Food, Learning, Fashion) — cheap, and sharpens
`search_context` style a lot.

### 8.4 Embedding

```
embedding_input = "\n".join(filter(None, [
    title, summary, search_context,
    ", ".join(keywords), ", ".join(entities)]))
```
→ `gemini-embedding-001`, `task_type="RETRIEVAL_DOCUMENT"`,
`output_dimensionality=768` → **L2-normalize** → store, along with
`embedding_input` itself (when a result is wrong, the first question is always
"what did we actually embed?").

Query side uses the identical model + dims with `RETRIEVAL_QUERY` and the same
normalization (D2/D3).

### 8.5 Media ladder — always analyze the media (D15)

**The rule the spike got wrong: media analysis is never gated on caption
length.** Every post gets its media looked at. Caption length is not caption
informativeness — long captions are frequently hashtag spam, and short ones
("Mongo possets 🥭") sit on the most visually distinctive posts.

| rung | condition | sent to Gemini |
|---|---|---|
| 1. `frames` | `media_type='video'`, `video_url` resolvable, ≤ `VIDEO_MAX_MB` | `MEDIA_MAX_FRAMES` evenly-spaced JPEG frames + caption |
| 2. `image` | otherwise, `media_storage_path` exists | thumbnail JPEG + caption |
| 3. `caption` | no usable media | caption only; keep `search_context` conservative |

- Frames: evenly spaced across the whole video (`total_frames // max_frames`),
  downscaled to `MEDIA_FRAME_WIDTH × MEDIA_FRAME_HEIGHT`. Validated at 12 frames
  @ 480×854. Do **not** drop below that resolution — reels are dense with small
  on-screen text and OCR degrades fast.
- **Never persist video files.** Download → extract → analyze → delete, in a
  `try/finally`. 85 reels of video would eat the 1 GB Storage tier. Only the
  thumbnail is stored (D4).
- Carousels: analyze `childPosts[*].displayUrl` up to a small cap.
- Record the rung in `content_analysis.analysis_input_mode` and the frame count
  in `frames_analyzed`.

**Open question, to be settled by §9.1 and not by argument:** Gemini also
accepts native video, which is 1-FPS frames **plus the timestamped audio
track**. Narration ("a splash of lime is the trick") is signal that extracted
frames discard entirely. Frames are proven and cheaper; native video is richer.
Run 40 posts each way, compare recall@5, keep the winner. `analysis_input_mode`
exists so this is a query, not a re-run.

**Acceptance for Phase 3:** all posts `COMPLETED` or explainably `FAILED`.
Spot-check 10 rows: is `search_context` describing the *media*, or echoing the
caption? If it's echoing, fix the prompt and rerun **before** Phase 4.

---

## 9. Phase 4 — Search, verified from the CLI before any UI

`python -m pipeline.cli search "<query>"` prints top 10 with score, `fts_rank`,
`semantic_rank`, title, category, creator, URL. Showing both ranks makes it
obvious which retriever is carrying a query.

Smoke queries: `mango dessert`, `that quick mango recipe`, `restaurants in
Tokyo`, `black wedding outfit`, `home decor with brown furniture`, `Kafka
tutorials`, plus 5 vague ones about posts you actually remember.

### 9.1 Eval harness (D11)

`eval/queries.json` — ~25 entries written **from memory, before looking at the
DB**:

```json
[{ "query": "that quick mango dessert with yogurt", "expect_shortcode": "C1a2b3c4" }]
```

`run_eval.py` reports **recall@5**, recall@10, MRR. Record the baseline in §11.
**Rule: no retrieval change ships without a before/after number.**
Target recall@5 ≥ 0.85.

### 9.2 If quality is short, in this order
1. Improve the `search_context`/keywords prompt and reprocess (biggest lever).
2. Tune `rrf_k` / `fts_weight` / `semantic_weight`.
3. Add `pg_trgm` fuzzy matching on `title` as a third RRF arm (typos).
4. A/B frames vs native video (§8.5).
5. *Only then* consider Gemini query expansion — measure that it helps first.

---

## 10. Phase 5–6 — UI

Next.js App Router + Tailwind, all data server-side (D5).

- **`middleware.ts`**: no valid signed cookie and path isn't `/login` → redirect.
  `/login` POSTs `APP_PASSWORD`, sets HttpOnly/Secure/SameSite=Lax cookie (HMAC
  of a timestamp with `APP_SESSION_SECRET`, ~90 days). That's the whole auth story.
- **`/` dashboard**: large search input, placeholder *"What do you remember about
  the post?"*; total count; per-category counts; status line
  `85 total · 83 processed · 0 processing · 2 failed`. Results inline below —
  thumbnail, title, category · subcategory, creator, one-line summary.
  Reveal `search_context` on hover/expand: when a result looks wrong it
  immediately explains *why* it matched.
- **`/library`**: responsive grid, category filter chips, `saved_at` desc, 48/page.
  Card = thumbnail, title, category/subcategory, creator, 3 keyword tags.
- **`/post/[id]`**: media, title, summary, search_context, creator, saved date,
  link out, keywords, and **category-specific rendering** of `ai_metadata`
  (ingredients/time for Food; city/country/place_type for Travel; …). Generic
  key/value table for unknown shapes — never hide data.
- Images: signed URL or small server route from the private bucket.
- **Phase 6** `/status`: FAILED posts with `processing_error` + `retry_count`,
  a Retry button (`POST /api/retry` → `PENDING`, `retry_count=0`), and a
  documented reprocess-by-`prompt_version` path.

---

## 11. Phase status

| Phase | Status | Notes |
|---|---|---|
| 0. Scaffold (pipeline pkg, web app, .gitignore, .env.example) | ☐ | |
| 1. Supabase schema + indexes + `hybrid_search` | ☑ | Written and **verified against pgvector/pg16 in Docker**: all 3 migrations apply cleanly and are idempotent; RRF fusion, FTS-only rescue, semantic-only rescue, stopword-only queries, category filter, stemming, weight skew, `updated_at` trigger, generated-column refresh, and cascade delete all confirmed. Still needs applying to the real Supabase project. |
| 2. Ingestion (parse-export → scrape → ingest → fetch-media) | ☐ | export has 85 posts |
| 3. AI worker | ☐ | COMPLETED/FAILED: — |
| 4. CLI search verified + eval baseline | ☐ | recall@5: — |
| 5. UI (dashboard, library, detail) | ☐ | |
| 6. Status/retry UI, filters | ☐ | |
| 7. Deploy to Vercel + keep-alive cron | ☐ | |

**Gate:** do not start Phase 5 until Phase 4's eval number is recorded above.
UI built on bad retrieval just hides the problem.

---

## 12. Risks

- **R1 — Gemini quota.** Largely defused by D14 (1,500 RPD vs ~170 calls needed).
  `WORKER_DAILY_CAP` + resumability stay as a safety net. Watch TPM rather than
  RPD, since frames are token-heavy — keep `WORKER_RPM` ≈ 10 and measure real
  usage with `count_tokens` on the first batch.
- **R1b — `gemini-3.1-flash-lite` is preview.** No SLA; can change underneath you.
  `GEMINI_ANALYSIS_FALLBACK_MODEL` + per-row `ai_model` make a swap a config
  change plus a selective reprocess.
- **R2 — Instagram CDN URLs expire, video URLs included.** Mitigated by D4/D15.
  Run fetch-media and the worker within days of scraping or the reels can no
  longer be analyzed at all.
- **R3 — Supabase pauses (7 days idle).** Mitigated by D6; data is retained.
- **R4 — Apify schema drift.** Read defensively; `raw_apify_data` means a
  normalization bug is fixable without re-scraping.
- **R5 — `search_context` degenerates into caption paraphrase.** The main quality
  failure mode. Caught by eyeballing 10 rows after Phase 3 and by the eval set.
  `prompt_version` makes the fix a reprocess, not a re-scrape.
- **R6 — Export format changes.** Defensive `label_values` walker, plus the
  mojibake fixup (§7.1).
- **R7 — Accidental spend.** `--confirm` + printed estimate on scrape; no payment
  method anywhere; free plans only.

## 13. Explicitly not building

No billing, multi-tenancy, real auth beyond the password gate, Kafka/Redis/K8s,
automatic Instagram sync, or Instagram credential collection. Incremental sync
stays export-file-based — dedup by `instagram_post_id` already does the hard
part, but it is not built now.
