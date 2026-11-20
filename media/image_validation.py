"""Validate uploaded raster images before they reach Storage or the renderer."""
from io import BytesIO

MAX_IMAGE_PIXELS = 16_000_000

_EXTENSION_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
}


def validate_image_bytes(data: bytes, suffix: str) -> None:
    """Validate actual file format and pixel count without fully decoding the image."""
    from PIL import Image, UnidentifiedImageError

    expected_format = _EXTENSION_FORMATS.get(suffix.lower())
    if expected_format is None:
        raise ValueError("Unsupported image extension")

    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != expected_format:
                raise ValueError(
                    f"The file content is {image.format or 'unknown'}, but its extension "
                    f"expects {expected_format}."
                )
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Image dimensions must not exceed {MAX_IMAGE_PIXELS:,} pixels total."
                )
            image.verify()
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("The uploaded file is not a valid supported image.") from exc
