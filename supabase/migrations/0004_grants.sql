-- ============================================================================
-- Search My Saves — 0004_grants.sql
-- Table privileges for service_role. Apply after 0001. Safe to re-run.
--
-- 0001 creates the tables but grants nothing -- on a fresh Supabase project
-- service_role has zero access until this runs, and every pipeline query
-- (even a plain select) fails with 42501 "permission denied for table ...".
-- The pipeline authenticates exclusively as service_role (db.py), so it
-- needs full CRUD here, not just select.
-- ============================================================================

grant select, insert, update, delete on public.saved_posts to service_role;
grant select, insert, update, delete on public.content_analysis to service_role;

-- library_stats (0001) is a separate object from the tables it's built on --
-- granting the tables above does not implicitly grant the view itself.
grant select on public.library_stats to service_role;
