"""Versioned prompts and JSON schemas for the two LLM stages.

Versions are bumped any time the prompt or schema changes meaningfully; the
worker can use them to decide whether to re-run a stage on existing rows
(future work — Plan 1 records only the latest result).
"""

from __future__ import annotations

from typing import Any

STAGE_A_VERSION: str = "stage_a/v1"
STAGE_B_VERSION: str = "stage_b/v1"

STAGE_A_PROMPT: str = (
    "Look at this photograph and decide whether its primary subject is "
    "food or a prepared dish (including drinks, snacks, desserts, "
    "ingredients arranged for a meal). Photos of people eating count as "
    "food only if the food itself is prominent in the frame. Photos of "
    "menus, restaurant interiors without dishes, or empty plates do not "
    "count.\n\n"
    "Respond with a structured classification including a confidence "
    "score between 0.0 (definitely not food) and 1.0 (definitely food)."
)

STAGE_A_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_food": {
            "type": "boolean",
            "description": "True if the photo primarily depicts food/dish.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence in the is_food classification.",
        },
    },
    "required": ["is_food", "confidence"],
}

STAGE_B_PROMPT: str = (
    "This photograph depicts food. Identify the specific dish and its "
    "cuisine. Be specific about the dish (e.g., 'tonkotsu ramen' not "
    "just 'noodles'). For cuisine, use a short canonical label like "
    "'Japanese', 'Italian', 'Mexican', 'Cantonese', 'Thai', 'American', "
    "'Indian', etc. If you can't determine cuisine, use 'Unknown'.\n\n"
    "Provide a confidence score from 0.0 (uncertain) to 1.0 (highly "
    "confident in both dish and cuisine)."
)

STAGE_B_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dish_name": {
            "type": "string",
            "description": "Specific dish name, e.g. 'margherita pizza'.",
        },
        "cuisine": {
            "type": "string",
            "description": "Canonical cuisine label, e.g. 'Italian'.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
    "required": ["dish_name", "cuisine", "confidence"],
}

__all__ = [
    "STAGE_A_PROMPT",
    "STAGE_A_SCHEMA",
    "STAGE_A_VERSION",
    "STAGE_B_PROMPT",
    "STAGE_B_SCHEMA",
    "STAGE_B_VERSION",
]
