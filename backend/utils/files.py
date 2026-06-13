"""File upload validation utilities."""

import io
from typing import Tuple

import cv2
import numpy as np

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}


def validate_image_bytes(data: bytes) -> str:
    """Validate size and magic bytes; return MIME type or raise ValueError."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Image exceeds 5MB limit")
    if len(data) < 12:
        raise ValueError("Invalid image file")
    mime = None
    for magic, mimetype in ALLOWED_MAGIC.items():
        if data.startswith(magic):
            mime = mimetype
            break
    if mime is None:
        raise ValueError("Only JPEG and PNG images are accepted")
    return mime


def decode_image(data: bytes) -> np.ndarray:
    """Decode image bytes to BGR numpy array."""
    validate_image_bytes(data)
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image")
    return image
