"""DEIMv2-wholebody49 person detector via ONNX Runtime.

49-keypoint index map (body 0-16, feet 17-22, hands 23-48):
  Body: nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles
  Feet: left/right toes and heels
  Hands: 13 points per hand
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

from backend.config import get_settings


def _nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.5) -> np.ndarray:
    """Return indices to keep after NMS."""
    if len(boxes) == 0:
        return np.array([], dtype=np.int64)
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]
    return np.array(keep, dtype=np.int64)


class PersonDetector:
    """DEIMv2 wholebody49 ONNX wrapper."""

    def __init__(self, model_path: Optional[Path] = None, confidence_threshold: Optional[float] = None) -> None:
        settings = get_settings()
        path = model_path or settings.deimv2_model_path
        self.confidence_threshold = confidence_threshold or settings.DEIMV2_CONFIDENCE_THRESHOLD
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.input_h = int(shape[2]) if isinstance(shape[2], int) else 640
        self.input_w = int(shape[3]) if isinstance(shape[3], int) else 640

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
        h, w = frame.shape[:2]
        scale = min(self.input_h / h, self.input_w / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(frame, (nw, nh))
        padded = np.zeros((self.input_h, self.input_w, 3), dtype=np.float32)
        padded[:nh, :nw] = resized.astype(np.float32)
        padded /= 255.0
        blob = padded.transpose(2, 0, 1)[np.newaxis, ...]
        return blob, scale, (w, h)

    def _parse_outputs(
        self, outputs: list[np.ndarray], scale: float, orig_size: tuple[int, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Parse ONNX outputs into boxes, scores, keypoints."""
        w, h = orig_size
        boxes_list: list[np.ndarray] = []
        scores_list: list[float] = []
        kpts_list: list[np.ndarray] = []

        for out in outputs:
            arr = np.asarray(out)
            if arr.ndim == 3 and arr.shape[-1] >= 4:
                # [batch, N, 4+score+keypoints] style
                for det in arr[0]:
                    score = float(det[4]) if det.shape[0] > 4 else 1.0
                    if score < self.confidence_threshold:
                        continue
                    box = det[:4].copy() / scale
                    box[0::2] = np.clip(box[0::2], 0, w)
                    box[1::2] = np.clip(box[1::2], 0, h)
                    boxes_list.append(box)
                    scores_list.append(score)
                    if det.shape[0] >= 4 + 1 + 49 * 3:
                        kp = det[5 : 5 + 49 * 3].reshape(49, 3).copy()
                        kp[:, :2] /= scale
                        kpts_list.append(kp)
                    elif det.shape[0] >= 4 + 1 + 17 * 3:
                        kp17 = det[5 : 5 + 17 * 3].reshape(17, 3).copy()
                        kp17[:, :2] /= scale
                        kp49 = np.zeros((49, 3), dtype=np.float32)
                        kp49[:17] = kp17
                        kpts_list.append(kp49)
                    else:
                        kpts_list.append(np.zeros((49, 3), dtype=np.float32))

        if not boxes_list and len(outputs) >= 2:
            # Separate boxes/scores tensors
            boxes_raw = np.asarray(outputs[0]).reshape(-1, 4)
            scores_raw = np.asarray(outputs[1]).reshape(-1)
            kpts_raw = np.asarray(outputs[2]) if len(outputs) > 2 else None
            for i, score in enumerate(scores_raw):
                if float(score) < self.confidence_threshold:
                    continue
                box = boxes_raw[i].copy() / scale
                box[0::2] = np.clip(box[0::2], 0, w)
                box[1::2] = np.clip(box[1::2], 0, h)
                boxes_list.append(box)
                scores_list.append(float(score))
                if kpts_raw is not None and i < len(kpts_raw):
                    kp = np.asarray(kpts_raw[i]).reshape(-1, 3).copy()
                    if kp.shape[0] >= 49:
                        kp = kp[:49]
                    else:
                        kp49 = np.zeros((49, 3), dtype=np.float32)
                        kp49[: kp.shape[0]] = kp
                        kp = kp49
                    kp[:, :2] /= scale
                    kpts_list.append(kp.astype(np.float32))
                else:
                    kpts_list.append(np.zeros((49, 3), dtype=np.float32))

        if not boxes_list:
            return (
                np.zeros((0, 4), dtype=np.float32),
                np.zeros((0,), dtype=np.float32),
                np.zeros((0, 49, 3), dtype=np.float32),
            )

        boxes = np.stack(boxes_list).astype(np.float32)
        scores = np.array(scores_list, dtype=np.float32)
        keypoints = np.stack(kpts_list).astype(np.float32)

        keep = _nms_xyxy(boxes, scores)
        return boxes[keep], scores[keep], keypoints[keep]

    def detect(self, frame: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Detect persons; returns boxes (N,4), scores (N,), keypoints (N,49,3)."""
        blob, scale, orig_size = self._preprocess(frame)
        outputs = self.session.run(None, {self.input_name: blob})
        return self._parse_outputs(outputs, scale, orig_size)
