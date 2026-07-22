"""OpenAI Responses API — Image Generation tool schemas.

移植自 MiMo-Code packages/opencode/src/provider/sdk/copilot/responses/tool/image-generation.ts
"""

from __future__ import annotations

from typing import Any


def image_generation_args_schema() -> dict[str, Any]:
    """Return the JSON schema for image generation args."""
    return {
        "type": "object",
        "properties": {
            "background": {
                "type": "string",
                "enum": ["auto", "opaque", "transparent"],
                "description": "Background type (default: auto)",
            },
            "input_fidelity": {
                "type": "string",
                "enum": ["low", "high"],
                "description": "Input fidelity (default: low)",
            },
            "input_image_mask": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "image_url": {"type": "string"},
                },
                "description": "Optional mask for inpainting",
            },
            "model": {
                "type": "string",
                "description": "The image generation model (default: gpt-image-1)",
            },
            "moderation": {
                "type": "string",
                "enum": ["auto"],
                "description": "Moderation level",
            },
            "output_compression": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Compression level (default: 100)",
            },
            "output_format": {
                "type": "string",
                "enum": ["png", "jpeg", "webp"],
                "description": "Output format (default: png)",
            },
            "partial_images": {
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "Partial images for streaming",
            },
            "quality": {
                "type": "string",
                "enum": ["auto", "low", "medium", "high"],
                "description": "Image quality (default: auto)",
            },
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1024x1536", "1536x1024", "auto"],
                "description": "Image size (default: auto)",
            },
        },
        "additionalProperties": False,
    }


def image_generation_output_schema() -> dict[str, Any]:
    """Return the JSON schema for image generation output."""
    return {
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "description": "The generated image (base64 encoded)",
            },
        },
        "required": ["result"],
    }
