-- ============================================================================
-- Search My Saves — 0002_indexes.sql
-- Retrieval indexes. Apply after 0001. Safe to re-run.
-- ============================================================================

-- ── keyword arm: GIN over the weighted tsvector ─────────────────────────────
create index if not exists content_analysis_fts_idx
  on content_analysis using gin (search_document);


-- ── semantic arm: HNSW over the embedding ───────────────────────────────────
-- vector_cosine_ops because embeddings are L2-normalized (plan.md D3), which
-- makes cosine distance equivalent to inner product and keeps <=> meaningful.
--
-- At ~85 rows Postgres will usually seq-scan anyway and that is FINE — exact
-- search over 85 vectors is sub-millisecond. This index exists so nothing has
-- to change at 5,000+ posts.
create index if not exists content_analysis_embedding_idx
  on content_analysis using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);


-- ── filtering / browsing ────────────────────────────────────────────────────
create index if not exists content_analysis_category_idx
  on content_analysis (category);

-- keyword-chip filtering on the library page
create index if not exists content_analysis_keywords_idx
  on content_analysis using gin (keywords);

-- selective reprocessing: "re-run everything still on prompt v1" (plan.md D9)
create index if not exists content_analysis_prompt_version_idx
  on content_analysis (prompt_version);

-- fuzzy title matching, reserved for the optional third RRF arm (plan.md §9.2)
create index if not exists content_analysis_title_trgm_idx
  on content_analysis using gin (title gin_trgm_ops);
