-- ============================================================================
-- Search My Saves — 0003_hybrid_search.sql
--
-- Hybrid retrieval: full-text + vector, fused with Reciprocal Rank Fusion,
-- as a single Postgres function callable via supabase.rpc('hybrid_search', ...)
-- (CLAUDE.md: RRF must live in the database, not in application code).
--
-- Why RRF and not weighted score blending: ts_rank_cd scores and cosine
-- distances live on incomparable scales, and their distributions shift per
-- query. RRF uses only *ranks*, so it needs no normalization and no per-query
-- calibration. score = sum over arms of weight / (rrf_k + rank).
--
-- Apply after 0002. Safe to re-run.
-- ============================================================================

create or replace function hybrid_search(
  query_text       text,
  query_embedding  vector(768),
  match_count      int   default 20,
  fts_weight       float default 1.0,
  semantic_weight  float default 1.0,
  rrf_k            int   default 50,
  filter_category  text  default null
)
returns table (
  post_id            uuid,
  score              float,
  fts_rank           int,
  semantic_rank      int,
  title              text,
  summary            text,
  search_context     text,
  category           text,
  subcategory        text,
  keywords           text[],
  ai_metadata        jsonb,
  instagram_url      text,
  creator_username   text,
  media_type         text,
  media_storage_path text,
  saved_at           timestamptz
)
language sql
stable
as $$
with
-- Candidate pool per arm. Over-fetch (3x) so a document ranked poorly by one
-- arm can still be rescued by the other during fusion.
params as (
  select
    websearch_to_tsquery('english', coalesce(query_text, '')) as tsq,
    greatest(match_count, 20) * 3                             as pool
),

-- ── arm 1: keyword / full-text ──────────────────────────────────────────────
-- Empty or stopword-only queries yield an empty tsquery that matches nothing;
-- that is fine, the semantic arm carries those.
fts as (
  select
    ca.post_id,
    row_number() over (
      order by ts_rank_cd(ca.search_document, params.tsq) desc, ca.post_id
    )::int as rank_ix
  from content_analysis ca, params
  where ca.search_document @@ params.tsq
    and (filter_category is null or ca.category = filter_category)
  order by rank_ix
  limit (select pool from params)
),

-- ── arm 2: semantic / vector ────────────────────────────────────────────────
-- <=> is cosine distance; embeddings are L2-normalized (plan.md D3).
semantic as (
  select
    ca.post_id,
    row_number() over (
      order by ca.embedding <=> query_embedding, ca.post_id
    )::int as rank_ix
  from content_analysis ca, params
  where ca.embedding is not null
    and (filter_category is null or ca.category = filter_category)
  order by ca.embedding <=> query_embedding
  limit (select pool from params)
)

-- ── fusion ──────────────────────────────────────────────────────────────────
-- FULL OUTER JOIN so a hit from either arm alone still surfaces; the missing
-- arm contributes 0 to the score via coalesce.
select
  coalesce(f.post_id, s.post_id) as post_id,
  ( coalesce(1.0 / (rrf_k + f.rank_ix), 0.0) * fts_weight
  + coalesce(1.0 / (rrf_k + s.rank_ix), 0.0) * semantic_weight )::float as score,
  f.rank_ix as fts_rank,
  s.rank_ix as semantic_rank,
  ca.title,
  ca.summary,
  ca.search_context,
  ca.category,
  ca.subcategory,
  ca.keywords,
  ca.ai_metadata,
  sp.instagram_url,
  sp.creator_username,
  sp.media_type,
  sp.media_storage_path,
  sp.saved_at
from fts f
full outer join semantic s on f.post_id = s.post_id
join content_analysis ca on ca.post_id = coalesce(f.post_id, s.post_id)
join saved_posts       sp on sp.id      = coalesce(f.post_id, s.post_id)
order by score desc, ca.title
limit match_count;
$$;

comment on function hybrid_search is
  'Hybrid keyword + vector retrieval fused with Reciprocal Rank Fusion. '
  'query_embedding must come from gemini-embedding-001 at 768 dims with '
  'task_type=RETRIEVAL_QUERY, L2-normalized — the same model and dimensionality '
  'used to build content_analysis.embedding. Tune fts_weight / semantic_weight / '
  'rrf_k against eval/queries.json, never by intuition (plan.md §9.1).';
