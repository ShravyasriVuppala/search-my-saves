-- ============================================================================
-- Search My Saves — 0001_schema.sql
--
-- Two tables, strictly separated (CLAUDE.md principles 1-3):
--   saved_posts      raw ingested data. Source of truth. Never mutated by AI.
--   content_analysis AI-derived data. Fully regenerable from saved_posts alone,
--                    without re-scraping Instagram.
--
-- Apply in the Supabase SQL editor, or via `supabase db push`.
-- Safe to re-run.
-- ============================================================================

create extension if not exists vector;      -- pgvector: embeddings + HNSW
create extension if not exists pg_trgm;     -- fuzzy title matching (search phase 2)


-- ============================================================================
-- saved_posts — raw, untouched
-- ============================================================================
create table if not exists saved_posts (
  id                 uuid primary key default gen_random_uuid(),

  -- identity / dedup. Instagram's shortcode; the only key ingestion dedups on.
  instagram_post_id  text not null unique,
  instagram_url      text not null,

  -- content
  creator_username   text,
  caption            text,           -- from Apify, falling back to export_caption
  export_caption     text,           -- from the Meta export; free Apify-less fallback
  alt_text           text,           -- Instagram's own accessibility description

  -- media
  media_type         text,           -- image | video | carousel
  product_type       text,           -- Apify productType; 'clips' = reel
  media_url          text,           -- displayUrl. SIGNED AND EXPIRING — see D4.
  video_url          text,           -- videoUrl. ALSO EXPIRING. Valid only inside
                                     -- the processing window; never rely on it later.
  video_duration     numeric,        -- seconds
  media_storage_path text,           -- D4: durable copy in Supabase Storage

  -- timeline
  posted_at          timestamptz,    -- when the creator posted it
  saved_at           timestamptz,    -- D10: when *I* saved it (from the export)
  collection_name    text,           -- D10: UNCONFIRMED — the per-post export records
                                     -- carry no collection field. Verify against the
                                     -- full export (plan.md §7.1); drop this column if
                                     -- it turns out to be unobtainable.

  -- provenance. Never delete or mutate: AI processing must be fully rerunnable
  -- from this column alone (CLAUDE.md principle 3).
  raw_apify_data     jsonb not null,
  imported_at        timestamptz not null default now(),

  -- processing state machine
  processing_status  text not null default 'PENDING'
    check (processing_status in ('PENDING','PROCESSING','COMPLETED','FAILED')),
  processing_error   text,
  retry_count        int  not null default 0,

  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

comment on column saved_posts.raw_apify_data is
  'Full Apify response, kept forever. Never delete or mutate — AI processing '
  'must be rerunnable from this table alone without re-scraping.';
comment on column saved_posts.media_url is
  'Instagram CDN URL. Signed and expires in days-to-weeks. Use media_storage_path '
  'for anything durable (UI rendering, re-analysis).';

-- worker claims `PENDING and retry_count < N ordered by saved_at desc`
create index if not exists saved_posts_worker_queue_idx
  on saved_posts (processing_status, retry_count, saved_at desc nulls last);

create index if not exists saved_posts_saved_at_idx
  on saved_posts (saved_at desc nulls last);


-- ============================================================================
-- helper: immutable text[] -> text
--
-- Postgres marks array_to_string() STABLE (for an arbitrary element type its
-- output function may be stable), so it cannot be used inside a generated
-- column. For text[] the operation is genuinely deterministic, so this thin
-- wrapper declares the immutability the planner needs.
-- ============================================================================
create or replace function text_array_to_string(arr text[])
returns text
language sql
immutable
parallel safe
returns null on null input
as $$
  select array_to_string(arr, ' ');
$$;


-- ============================================================================
-- content_analysis — AI-derived, one row per post
-- ============================================================================
create table if not exists content_analysis (
  post_id         uuid primary key references saved_posts(id) on delete cascade,

  -- classification
  category        text,   -- Food|Travel|Fashion|Home|Products|Learning|
                          -- Entertainment|Ideas|Other
  subcategory     text,

  -- human-readable
  title           text,
  summary         text,

  -- THE primary retrieval signal: how I'd describe this from memory later.
  -- Describes visible content, not a caption restatement. See plan.md §8.3.
  search_context  text,

  keywords        text[] not null default '{}',
  entities        text[] not null default '{}',

  -- category-specific fields, schema-less by design (CLAUDE.md principle 5)
  ai_metadata     jsonb  not null default '{}'::jsonb,

  -- vector search
  embedding       vector(768),   -- gemini-embedding-001 @ 768 dims, L2-normalized
  embedding_input text,          -- exact string embedded. Debugging: "what did we
                                 -- actually embed?" is always the first question.

  -- D12: denormalized caption + creator so the tsvector below can stay a
  -- single-table generated column (generated columns cannot cross tables).
  source_text     text,

  -- provenance, for selective reprocessing (D9/D14/D15)
  ai_model            text,   -- which Gemini model produced this
  prompt_version      text,   -- bump on every meaningful prompt change
  analysis_input_mode text    -- frames | image | caption
    check (analysis_input_mode is null
           or analysis_input_mode in ('frames','video','image','caption')),
  frames_analyzed     int,
  ai_processed_at     timestamptz not null default now(),

  -- D12: weighted full-text document, always in sync with the columns above.
  -- Weights: title A > keywords/entities B > summary C > context/caption D.
  search_document tsvector generated always as (
      setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'A') ||
      setweight(to_tsvector('english'::regconfig,
          coalesce(text_array_to_string(keywords), '') || ' ' ||
          coalesce(text_array_to_string(entities), '')), 'B') ||
      setweight(to_tsvector('english'::regconfig, coalesce(summary, '')), 'C') ||
      setweight(to_tsvector('english'::regconfig,
          coalesce(search_context, '') || ' ' || coalesce(source_text, '')), 'D')
  ) stored
);

comment on column content_analysis.search_context is
  'Main retrieval signal. 2-4 sentences describing what a person would remember '
  'about this post later — visual content, not a caption restatement.';
comment on column content_analysis.embedding is
  'gemini-embedding-001, output_dimensionality=768, L2-normalized so cosine '
  'distance behaves. Query side must use identical model/dims with '
  'task_type=RETRIEVAL_QUERY.';


-- ============================================================================
-- keep updated_at honest
-- ============================================================================
create or replace function touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists saved_posts_touch on saved_posts;
create trigger saved_posts_touch
  before update on saved_posts
  for each row execute function touch_updated_at();


-- ============================================================================
-- convenience view: dashboard counts without two round trips
-- ============================================================================
create or replace view library_stats as
select
  count(*)                                                        as total,
  count(*) filter (where processing_status = 'COMPLETED')         as completed,
  count(*) filter (where processing_status = 'PROCESSING')        as processing,
  count(*) filter (where processing_status = 'PENDING')           as pending,
  count(*) filter (where processing_status = 'FAILED')            as failed
from saved_posts;
