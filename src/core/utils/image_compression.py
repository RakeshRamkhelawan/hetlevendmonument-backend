"""
SC-9.2: Image Compression Utilities
Provides image optimization and compression functions.
"""

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

logger = logging.getLogger(__name__)

# Try to import Pillow
try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    PILLOW_AVAILABLE = False
    Image = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from PIL.Image import Image as ImageType


@dataclass
class ImageInfo:
    """Information about a processed image."""

    width: int
    height: int
    format: str
    original_size: int
    compressed_size: int
    compression_ratio: float


class ImageCompressor:
    """
    SC-9.2: Image compression and optimization utility.

    Provides:
    - JPEG/PNG compression
    - Resizing with aspect ratio preservation
    - Thumbnail generation
    - WebP conversion
    """

    DEFAULT_QUALITY = 85
    MAX_DIMENSION = 2048
    THUMBNAIL_SIZE = (150, 150)

    def __init__(self) -> None:
        if not PILLOW_AVAILABLE:
            logger.warning("Pillow not installed. Image compression disabled.")

    def compress(
        self,
        image_data: bytes,
        quality: int | None = None,
        max_width: int | None = None,
        max_height: int | None = None,
        output_format: str | None = None,
    ) -> tuple[bytes, ImageInfo]:
        """
        Compress an image.

        Args:
            image_data: Raw image bytes
            quality: JPEG quality (1-100)
            max_width: Maximum width (preserves aspect ratio)
            max_height: Maximum height (preserves aspect ratio)
            output_format: Output format (JPEG, PNG, WEBP)

        Returns: Tuple[Any, ...] of (compressed_bytes, image_info)  # TODO(TYPE): replace Any with concrete type
        """
        if not PILLOW_AVAILABLE or Image is None:
            raise RuntimeError("Pillow not installed")

        quality = quality or self.DEFAULT_QUALITY
        original_size = len(image_data)

        # Open image
        img: "ImageType" = Image.open(io.BytesIO(image_data))
        original_format = img.format or "JPEG"

        # Convert RGBA to RGB for JPEG
        if img.mode == "RGBA" and (output_format or original_format).upper() == "JPEG":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB" and img.mode != "RGBA":
            img = img.convert("RGB")

        # Resize if needed
        if max_width or max_height:
            img = self._resize_with_aspect(img, max_width, max_height)

        # Determine output format
        out_format = (output_format or original_format).upper()
        if out_format == "JPG":
            out_format = "JPEG"

        # Compress
        output = io.BytesIO()

        if out_format == "JPEG":
            img.save(output, format="JPEG", quality=quality, optimize=True)
        elif out_format == "PNG":
            img.save(output, format="PNG", optimize=True)
        elif out_format == "WEBP":
            img.save(output, format="WEBP", quality=quality)
        else:
            img.save(output, format=out_format)

        compressed_data = output.getvalue()
        compressed_size = len(compressed_data)

        info = ImageInfo(
            width=img.width,
            height=img.height,
            format=out_format,
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=original_size / compressed_size if compressed_size > 0 else 1,
        )

        logger.info(
            f"Compressed image: {original_size} -> {compressed_size} bytes "
            f"({info.compression_ratio:.2f}x reduction)"
        )

        return compressed_data, info

    def create_thumbnail(self, image_data: bytes, size: tuple[int, int] | None = None) -> bytes:
        """Create a thumbnail from an image."""
        if not PILLOW_AVAILABLE or Image is None:
            raise RuntimeError("Pillow not installed")

        size = size or self.THUMBNAIL_SIZE

        img: "ImageType" = Image.open(io.BytesIO(image_data))

        # Convert mode if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Create thumbnail (modifies in place)
        resampling = Image.Resampling.LANCZOS if Image else Image.Resampling.LANCZOS
        img.thumbnail(size, resampling)

        output = io.BytesIO()
        img.save(output, format="JPEG", quality=80, optimize=True)

        return output.getvalue()

    def convert_to_webp(self, image_data: bytes, quality: int = 85) -> bytes:
        """Convert image to WebP format."""
        compressed, _ = self.compress(image_data, quality=quality, output_format="WEBP")
        return compressed

    def get_dimensions(self, image_data: bytes) -> tuple[int, int]:
        """Get image dimensions without full decode."""
        if not PILLOW_AVAILABLE or Image is None:
            raise RuntimeError("Pillow not installed")

        img: "ImageType" = Image.open(io.BytesIO(image_data))
        return img.width, img.height

    def _resize_with_aspect(
        self,
        img: "ImageType",
        max_width: int | None = None,
        max_height: int | None = None,
    ) -> "ImageType":
        """Resize image preserving aspect ratio."""
        width, height = img.size

        max_width = max_width or self.MAX_DIMENSION
        max_height = max_height or self.MAX_DIMENSION

        # Calculate scaling factor
        width_ratio = max_width / width if width > max_width else 1
        height_ratio = max_height / height if height > max_height else 1
        ratio = min(width_ratio, height_ratio)

        if ratio < 1:
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            resampling = Image.Resampling.LANCZOS  # pyright: ignore[reportOptionalMemberAccess]
            img = img.resize((new_width, new_height), resampling)

        return img


# Singleton instance
image_compressor = ImageCompressor()


# Convenience functions
def compress_image(image_data: bytes, quality: int = 85) -> bytes:
    """Compress an image with default settings."""
    compressed, _ = image_compressor.compress(image_data, quality=quality)
    return compressed


def create_thumbnail(image_data: bytes) -> bytes:
    """Create a thumbnail with default size."""
    return image_compressor.create_thumbnail(image_data)
