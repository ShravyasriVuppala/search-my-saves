/**
 * Mirrors supabase/migrations/0001_schema.sql and 0003_hybrid_search.sql.
 * Kept in sync by hand (plan.md D13) -- there's no generated-types codegen
 * step in this project, so a schema change means updating this file too.
 */

export type ProcessingStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

export type Category =
  | "Movies"
  | "Fashion"
  | "Beauty"
  | "Hairstyles"
  | "Food"
  | "Travel"
  | "Photo poses"
  | "Tech"
  | "Fitness"
  | "Dance"
  | "Art"
  | "Editing"
  | "Kids"
  | "Other";

export type MediaType = "image" | "video" | "carousel";

export type AnalysisInputMode = "frames" | "video" | "image" | "caption";

export interface SavedPost {
  id: string;
  instagram_post_id: string;
  instagram_url: string;
  creator_username: string | null;
  caption: string | null;
  export_caption: string | null;
  alt_text: string | null;
  media_type: MediaType | null;
  product_type: string | null;
  media_url: string | null;
  video_url: string | null;
  video_duration: number | null;
  media_storage_path: string | null;
  posted_at: string | null;
  saved_at: string | null;
  collection_name: string | null;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface ContentAnalysis {
  post_id: string;
  category: Category | null;
  subcategory: string | null;
  title: string | null;
  summary: string | null;
  search_context: string | null;
  keywords: string[];
  entities: string[];
  ai_metadata: Record<string, unknown>;
  ai_model: string | null;
  prompt_version: string | null;
  analysis_input_mode: AnalysisInputMode | null;
  frames_analyzed: number | null;
  ai_processed_at: string;
}

/** Row shape returned by the hybrid_search() RPC (0003_hybrid_search.sql). */
export interface SearchResult {
  post_id: string;
  score: number;
  fts_rank: number | null;
  semantic_rank: number | null;
  title: string | null;
  summary: string | null;
  search_context: string | null;
  category: Category | null;
  subcategory: string | null;
  keywords: string[];
  ai_metadata: Record<string, unknown>;
  instagram_url: string;
  creator_username: string | null;
  media_type: MediaType | null;
  media_storage_path: string | null;
  saved_at: string | null;
}

/** Row shape of the library_stats view. */
export interface LibraryStats {
  total: number;
  completed: number;
  processing: number;
  pending: number;
  failed: number;
}

/** Row shape of the category_counts view. */
export interface CategoryCount {
  category: Category;
  count: number;
}

export const CATEGORIES: Category[] = [
  "Movies",
  "Fashion",
  "Beauty",
  "Hairstyles",
  "Food",
  "Travel",
  "Photo poses",
  "Tech",
  "Fitness",
  "Dance",
  "Art",
  "Editing",
  "Kids",
  "Other",
];
