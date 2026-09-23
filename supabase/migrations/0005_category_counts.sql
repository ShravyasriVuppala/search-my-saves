-- ============================================================================
-- Search My Saves — 0005_category_counts.sql
-- Per-category post counts for the dashboard (CLAUDE.md: dashboard shows
-- "per-category counts", never implemented until now). Apply after 0001.
-- Safe to re-run.
--
-- Only COMPLETED posts have a category (content_analysis.category is null
-- until AI processing finishes), so this naturally excludes PENDING/FAILED
-- posts from the breakdown rather than showing a misleading "null" bucket.
-- ============================================================================

create or replace view category_counts as
select category, count(*) as count
from content_analysis
where category is not null
group by category
order by count desc;

grant select on public.category_counts to service_role;
