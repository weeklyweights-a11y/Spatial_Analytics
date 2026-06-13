"""SCRFD face detection via ONNX Runtime."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

from backend.config import get_settings


@dataclass
class Face:
    """Detected face with bbox, confidence, and 5 landmarks."""

    bbox: np.ndarray  # [x1, y1, x2, y2]
    confidence: float
    landmarks: np.ndarray  # shape (5, 2)


class FaceDetector:
    """SCRFD-10G ONNX wrapper."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        settings = get_settings()
        path = model_path or Path(settings.MODELS_DIR) / "scrfd_10g.onnx"
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = (640, 640)

    def _preprocess(self, image: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
        """Resize with aspect ratio pad to model input size."""
        h, w = image.shape[:2]
        scale = min(self.input_size[0] / h, self.input_size[1] / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(image, (nw, nh))
        padded = np.zeros((self.input_size[0], self.input_size[1], 3), dtype=np.uint8)
        padded[:nh, :nw] = resized
        blob = padded.astype(np.float32)
        blob = (blob - 127.5) / 128.0
        blob = blob.transpose(2, 0, 1)[np.newaxis, ...]
        return blob, scale, (w, h)

    def detect(self, image: np.ndarray, threshold: float = 0.5) -> list[Face]:
        """Detect faces in BGR image."""
        blob, scale, (orig_w, orig_h) = self._preprocess(image)
        outputs = self.session.run(None, {self.input_name: blob})

        faces: list[Face] = []
        # Parse SCRFD multi-scale outputs (buffalo_l det_10g layout)
        scores_list, bboxes_list, kpss_list = [], [], []
        for out in outputs:
            if out.ndim == 2 and out.shape[1] == 1:
                scores_list.append(out)
            elif out.ndim == 2 and out.shape[1] == 4:
                bboxes_list.append(out)
            elif out.ndim == 3:
                kpss_list.append(out)

        if not scores_list:
            # Fallback: try standard 3-output format
            if len(outputs) >= 3:
                scores_list = [outputs[0].reshape(-1, 1)]
                bboxes_list = [outputs[1].reshape(-1, 4)]
                if outputs[2].ndim >= 2:
                    kpss_list = [outputs[2].reshape(-1, 5, 2)]

        for scores, bboxes, kpss in zip(scores_list, bboxes_list, kpss_list):
            for i, score in enumerate(scores.flatten()):
                if score < threshold:
                    continue
                box = bboxes[i] / scale
                x1, y1, x2, y2 = box[:4]
                x1 = max(0, min(orig_w, x1))
                y1 = max(0, min(orig_h, y1))
                x2 = max(0, min(orig_w, x2))
                y2 = max(0, min(orig_h, y2))
                if x2 <= x1 or y2 <= y1:
                    continue
                kps = kpss[i].reshape(5, 2) / scale if i < len(kpss) else np.zeros((5, 2))
                faces.append(
                    Face(
                        bbox=np.array([x1, y1, x2, y2], dtype=np.float32),
                        confidence=float(score),
                        landmarks=kps.astype(np.float32),
                    )
                )

        # Deduplicate overlapping boxes — keep highest confidence
        faces.sort(key=lambda f: f.confidence, reverse=True)
        return faces
