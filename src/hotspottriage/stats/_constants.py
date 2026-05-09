"""Constants for block cache rows."""

DERIVED_BLOCK_CACHE_KEYS = frozenset(
    {
        "score",
        "score_band",
        "score_subscores",
        "score_driver",
        "score_explanation",
        "score_final_weights",
        "score_norm_inputs",
    }
)

BLOCK_CACHE_META_KEYS = frozenset({"_blob_sha", "_start", "_end"})
