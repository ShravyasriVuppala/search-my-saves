import "server-only";
import { GoogleGenAI } from "@google/genai";

import { envIntOr, envOr } from "@/lib/env";
import { getSupabaseClient } from "@/lib/supabase";
import type { Category, SearchResult } from "@/lib/types";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set.`);
  return value;
}

/**
 * RETRIEVAL_QUERY side of plan.md D2/D3. Must use the identical model and
 * output_dimensionality the pipeline used for RETRIEVAL_DOCUMENT
 * (pipeline/gemini/embed.py) or the vectors aren't comparable -- both read
 * from the same env var names so that invariant holds by construction, not
 * by convention.
 */
async function embedQuery(query: string): Promise<number[]> {
  const apiKey = requireEnv("GEMINI_API_KEY");
  const model = envOr("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001");
  const outputDimensionality = envIntOr("GEMINI_EMBEDDING_DIM", 768);

  const ai = new GoogleGenAI({ apiKey });
  const response = await ai.models.embedContent({
    model,
    contents: query,
    config: {
      taskType: "RETRIEVAL_QUERY",
      outputDimensionality,
    },
  });

  const values = response.embeddings?.[0]?.values;
  if (!values) throw new Error("Gemini returned no embedding for the query.");

  // MRL-truncated embeddings aren't guaranteed unit-length (plan.md D3) --
  // must match the L2-normalization the pipeline applies when embedding
  // posts, or pgvector's cosine distance is comparing incompatible scales.
  const norm = Math.sqrt(values.reduce((sum, v) => sum + v * v, 0));
  return norm === 0 ? values : values.map((v) => v / norm);
}

export async function search(
  query: string,
  options: { limit?: number; category?: Category | null } = {},
): Promise<SearchResult[]> {
  const { limit = 10, category = null } = options;
  const embedding = await embedQuery(query);
  const supabase = getSupabaseClient();

  const { data, error } = await supabase.rpc("hybrid_search", {
    query_text: query,
    query_embedding: embedding,
    match_count: limit,
    filter_category: category,
  });

  if (error) throw new Error(`hybrid_search failed: ${error.message}`);
  return (data ?? []) as SearchResult[];
}
