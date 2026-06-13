"""ArcFace embedding via ONNX Runtime."""

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

from backend.config import get_settings

# Standard 5-point reference for ArcFace alignment (112x112)
_ARCFACE_REF = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


class FaceRecognizer:
    """ArcFace-R100 ONNX wrapper."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        settings = get_settings()
        path = model_path or Path(settings.MODELS_DIR) / "arcface_r100.onnx"
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    @staticmethod
    def align_face(image: np.ndarray, landmarks: np.ndarray, size: int = 112) -> np.ndarray:
        """Affine warp using 5 SCRFD landmarks to 112x112."""
        ref = _ARCFACE_REF.copy()
        if size != 112:
            ref = ref * (size / 112.0)
        matrix, _ = cv2.estimateAffinePartial2D(landmarks.astype(np.float32), ref, method=cv2.LMEDS)
        if matrix is None:
            # Fallback crop from bbox center
            h, w = image.shape[:2]
            cx, cy = w // 2, h // 2
            half = min(w, h) // 2
            crop = image[max(0, cy - half) : cy + half, max(0, cx - half) : cx + half]
            return cv2.resize(crop, (size, size))
        return cv2.warpAffine(image, matrix, (size, size), borderValue=0)

    def embed(self, aligned_face: np.ndarray) -> np.ndarray:
        """Return 512-dim L2-normalized embedding."""
        face = aligned_face.astype(np.float32)
        if face.shape[:2] != (112, 112):
            face = cv2.resize(face, (112, 112))
        face = (face - 127.5) / 127.5
        face = face.transpose(2, 0, 1)[np.newaxis, ...]
        embedding = self.session.run(None, {self.input_name: face})[0].flatten()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32)
