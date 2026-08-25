"""Supabase client, service-role key. Pipeline-side only -- the web app never
imports this; it goes through its own server-side client (plan.md D5)."""

from supabase import Client, create_client

from config import Settings


def get_client(settings: Settings) -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
