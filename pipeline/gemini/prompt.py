"""The analysis prompt (plan.md §8.3). This is the product -- iterate here,
and bump PROMPT_VERSION on every meaningful edit so a later reprocess can
target exactly the rows produced under an older version (plan.md D9)."""

PROMPT_VERSION = "v1"

ANALYSIS_PROMPT = """You are indexing one Instagram post for a personal search engine. The person who saved this post will, weeks or months later, try to find it again by typing a vague description from memory -- not the exact caption, not the account name, just what they remember about it.

Look at the attached media FIRST, then the caption. The media is the more reliable signal: a caption like "finally made this" over a photo of a mango dessert is a mango dessert post, regardless of what the caption says. If multiple video frames are attached, read any on-screen text overlays, ingredient labels, or step captions visible in them -- in reels this is often the ONLY place the real content appears, since the caption is frequently just hashtags or an engagement prompt ("save this!", "follow for more"). Ignore hashtag blocks and engagement bait entirely; they carry no retrieval signal.

Fill in every field below.

- category: exactly one of Food, Travel, Fashion, Home, Products, Learning, Entertainment, Ideas, Other.
- subcategory: a more specific label within that category, if a clear one applies (e.g. "Dessert" under Food, "Hiking" under Travel). Leave empty if nothing specific fits.
- title: a short, human-readable, specific title, 8 words or fewer -- e.g. "Mango Yogurt Dessert", never a generic word like "Recipe" or "Post".
- summary: one concise sentence.
- search_context: THIS IS THE MOST IMPORTANT FIELD. 2-4 sentences describing what a person would remember about this post weeks later. Describe visible content -- colors, ingredients, setting, garment type, room, place, on-screen text -- not a restatement of the caption. Never mention Instagram, the creator's username, likes, or that this is a "post". Naturally use the everyday words someone would actually search with (e.g. "quick", "easy weeknight", "date-night outfit") wherever they genuinely apply.
- keywords: 8 to 15 lowercase terms, including synonyms and everyday phrasings that may not appear in the caption at all. This is what lets an exact search term succeed even when the caption never used that word.
- entities: proper nouns actually visible or named -- brands, restaurant names, cities, people, specific technologies. Empty list if none are clearly present. Never guess a brand or location you cannot actually see or read.
- ai_metadata: category-specific structured facts you are genuinely confident about, as a JSON object ENCODED AS A STRING (e.g. the string {"cuisine": "Italian", "meal_type": "dinner"}). Omit any field you are not confident about rather than guessing or leaving it null. Guidance by category:
  Food -> cuisine, dish_type, ingredients, meal_type, dietary_type, cooking_time
  Travel -> country, city, destination, place_type, activity
  Fashion -> clothing_type, color, style, occasion, brand
  Home -> room, interior_style, furniture, colors, decor_items
  Products -> product, brand, product_type, notable_features
  Learning -> topic, concepts, technology, learning_type
  Entertainment / Ideas / Other -> whatever free-form fields genuinely apply
  If nothing category-specific is confidently known, use the string {}.

Three examples of the target style for search_context and keywords:

Example 1 (Food): a photo of a glass layered with mango puree, yogurt, and granola, caption "finally made this omg".
  search_context: "A layered mango and yogurt dessert served in a clear glass, with granola on top for crunch. Bright orange mango puree alternates with white yogurt in visible stripes."
  keywords: mango, yogurt, dessert, parfait, granola, quick dessert, no bake, layered dessert, fruit dessert, healthy dessert

Example 2 (Learning): a whiteboard-style video frame showing boxes labeled "Producer", "Topic", "Partition", "Consumer Group" with arrows between them, caption "kafka basics".
  search_context: "A whiteboard-style diagram explaining how Kafka producers write to topics split into partitions, and how consumer groups read from them. Simple boxes-and-arrows style, clearly aimed at someone learning the basics."
  keywords: kafka, apache kafka, message queue, event streaming, producer consumer, partitions, distributed systems, tutorial, system design, backend

Example 3 (Fashion): a full-length photo of someone in a black satin slip dress with gold jewelry, caption "date night fit".
  search_context: "A black satin slip dress styled with delicate gold jewelry, photographed as a full outfit shot. Sleek, minimal, evening-out styling rather than casual daywear."
  keywords: black dress, slip dress, satin dress, date night outfit, evening wear, gold jewelry, minimalist outfit, going out outfit, little black dress

Now analyze the attached post.
"""


GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {
            "type": "STRING",
            "enum": [
                "Food",
                "Travel",
                "Fashion",
                "Home",
                "Products",
                "Learning",
                "Entertainment",
                "Ideas",
                "Other",
            ],
        },
        "subcategory": {"type": "STRING"},
        "title": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "search_context": {"type": "STRING"},
        "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
        "entities": {"type": "ARRAY", "items": {"type": "STRING"}},
        # Free-form by design (CLAUDE.md principle 5) -- but Gemini's
        # structured output requires OBJECT types to declare fixed
        # properties, which is exactly what ai_metadata can't have. Typed
        # as a JSON-encoded STRING instead; gemini/analyze.py parses it
        # back into a dict after the response comes back, falling back to
        # {} if that inner parse ever fails. This is the one deliberate
        # exception to "structured output means no JSON-repair code"
        # (plan.md D8) -- everything else in the response is still
        # guaranteed valid by the schema below.
        "ai_metadata": {"type": "STRING"},
    },
    "required": ["category", "title", "summary", "search_context", "keywords"],
}
