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


def _distance2bbox(points: np.ndarray, distance: np.ndarray, max_shape: tuple[int, int]) -> np.ndarray:
    """Convert distance predictions to xyxy boxes in input image space."""
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    x1 = np.clip(x1, 0, max_shape[1])
    y1 = np.clip(y1, 0, max_shape[0])
    x2 = np.clip(x2, 0, max_shape[1])
    y2 = np.clip(y2, 0, max_shape[0])
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance2kps(points: np.ndarray, distance: np.ndarray, max_shape: tuple[int, int]) -> np.ndarray:
    """Convert distance predictions to 5-point landmarks (N, 10)."""
    preds = []
    for i in range(0, distance.shape[1], 2):
        px = points[:, 0] + distance[:, i]
        py = points[:, 1] + distance[:, i + 1]
        px = np.clip(px, 0, max_shape[1])
        py = np.clip(py, 0, max_shape[0])
        preds.append(px)
        preds.append(py)
    return np.stack(preds, axis=-1)


def _anchor_centers(height: int, width: int, stride: int, num_anchors: int) -> np.ndarray:
    """Generate anchor center points for one FPN level."""
    anchor_centers = np.stack(np.mgrid[:height, :width][::-1], axis=-1).astype(np.float32)
    anchor_centers = (anchor_centers * stride).reshape((-1, 2))
    if num_anchors > 1:
        anchor_centers = np.stack([anchor_centers] * num_anchors, axis=1).reshape((-1, 2))
    return anchor_centers


class FaceDetector:
    """SCRFD-10G ONNX wrapper."""

    _strides = (8, 16, 32)
    _num_anchors = 2

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
        blob, scale, _orig_size = self._preprocess(image)
        outputs = self.session.run(None, {self.input_name: blob})

        scores_list: list[np.ndarray] = []
        bboxes_list: list[np.ndarray] = []
        kpss_list: list[np.ndarray] = []
        for out in outputs:
            if out.ndim == 2 and out.shape[1] == 1:
                scores_list.append(out)
            elif out.ndim == 2 and out.shape[1] == 4:
                bboxes_list.append(out)
            elif out.ndim == 2 and out.shape[1] == 10:
                kpss_list.append(out)

        input_h, input_w = self.input_size
        max_shape = (input_h, input_w)
        all_scores: list[float] = []
        all_boxes: list[np.ndarray] = []
        all_landmarks: list[np.ndarray] = []

        for idx, stride in enumerate(self._strides):
            if idx >= len(scores_list) or idx >= len(bboxes_list):
                break
            scores = scores_list[idx].reshape(-1)
            bbox_preds = bboxes_list[idx] * stride
            kps_preds = kpss_list[idx] * stride if idx < len(kpss_list) else None

            height = input_h // stride
            width = input_w // stride
            anchors = _anchor_centers(height, width, stride, self._num_anchors)
            boxes = _distance2bbox(anchors, bbox_preds, max_shape)

            pos_inds = np.where(scores >= threshold)[0]
            for i in pos_inds:
                box = boxes[i] / scale
                x1, y1, x2, y2 = box
                if x2 <= x1 or y2 <= y1:
                    continue
                if kps_preds is not None:
                    kps = _distance2kps(anchors, kps_preds, max_shape)[i].reshape(5, 2) / scale
                else:
                    kps = np.zeros((5, 2), dtype=np.float32)
                all_scores.append(float(scores[i]))
                all_boxes.append(box.astype(np.float32))
                all_landmarks.append(kps.astype(np.float32))

        if not all_scores:
            return []

        keep = self._nms(all_boxes, all_scores, iou_threshold=0.4)
        faces: list[Face] = []
        for i in keep:
            faces.append(
                Face(
                    bbox=all_boxes[i],
                    confidence=all_scores[i],
                    landmarks=all_landmarks[i],
                )
            )
        faces.sort(key=lambda f: f.confidence, reverse=True)
        return faces

    @staticmethod
    def _nms(boxes: list[np.ndarray], scores: list[float], iou_threshold: float) -> list[int]:
        """Greedy NMS; returns indices to keep."""
        if not boxes:
            return []
        arr = np.array(boxes, dtype=np.float32)
        order = np.argsort(scores)[::-1]
        keep: list[int] = []
        while order.size > 0:
            i = int(order[0])
            keep.append(i)
            if order.size == 1:
                break
            xx1 = np.maximum(arr[i, 0], arr[order[1:], 0])
            yy1 = np.maximum(arr[i, 1], arr[order[1:], 1])
            xx2 = np.minimum(arr[i, 2], arr[order[1:], 2])
            yy2 = np.minimum(arr[i, 3], arr[order[1:], 3])
            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h
            area_i = (arr[i, 2] - arr[i, 0]) * (arr[i, 3] - arr[i, 1])
            area_o = (arr[order[1:], 2] - arr[order[1:], 0]) * (arr[order[1:], 3] - arr[order[1:], 1])
            iou = inter / (area_i + area_o - inter + 1e-6)
            inds = np.where(iou <= iou_threshold)[0]
            order = order[inds + 1]
        return keep
