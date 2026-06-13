"""FAISS IndexFlatIP face matcher with embedding map persistence."""

import json
import threading
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

from backend.config import get_settings


class FaceMatcher:
    """Thread-safe FAISS face embedding index."""

    EMBEDDING_DIM = 512

    def __init__(self) -> None:
        settings = get_settings()
        self.index_path = Path(settings.FAISS_INDEX_PATH)
        self.map_path = Path(settings.EMBEDDING_MAP_PATH)
        self.index = faiss.IndexFlatIP(self.EMBEDDING_DIM)
        self._lock = threading.RLock()
        self._embedding_map: dict[int, str] = {}  # index_pos -> participant UUID
        self._registrations_since_save = 0
        self._save_every = 10

    def load(self) -> None:
        """Load index and embedding map from disk if present."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if self.index_path.exists():
            self.index = faiss.read_index(str(self.index_path))
        if self.map_path.exists():
            with open(self.map_path, encoding="utf-8") as f:
                raw = json.load(f)
                self._embedding_map = {int(k): v for k, v in raw.items()}

    def count(self) -> int:
        """Number of stored embeddings."""
        return self.index.ntotal

    def add(self, embedding: np.ndarray) -> int:
        """Add L2-normalized embedding; returns index position."""
        vec = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        with self._lock:
            pos = self.index.ntotal
            self.index.add(vec)
            self._registrations_since_save += 1
            return pos

    def set_participant_id(self, index_pos: int, participant_id: str) -> None:
        """Map FAISS index position to participant UUID."""
        with self._lock:
            self._embedding_map[index_pos] = participant_id

    def get_participant_id(self, index_pos: int) -> Optional[str]:
        """Reverse lookup participant UUID from FAISS position."""
        return self._embedding_map.get(index_pos)

    def search(self, embedding: np.ndarray, k: int = 1) -> tuple[float, int]:
        """Return (similarity, index_position) for best match."""
        if self.index.ntotal == 0:
            return 0.0, -1
        vec = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        similarities, indices = self.index.search(vec, k)
        sim = float(similarities[0][0])
        idx = int(indices[0][0])
        if idx < 0:
            return 0.0, -1
        return sim, idx

    def save(self) -> None:
        """Persist FAISS index and embedding_map.json atomically."""
        with self._lock:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(self.index_path))
            with open(self.map_path, "w", encoding="utf-8") as f:
                json.dump(self._embedding_map, f)
            self._registrations_since_save = 0

    def maybe_save(self) -> None:
        """Save every N registrations."""
        if self._registrations_since_save >= self._save_every:
            self.save()

    def remove_by_index(self, index_pos: int) -> None:
        """Rebuild index excluding one position (IndexFlatIP has no delete)."""
        with self._lock:
            if self.index.ntotal == 0:
                return
            all_vectors = faiss.rev_swig_ptr(self.index.get_xb(), self.index.ntotal * self.EMBEDDING_DIM)
            all_vectors = all_vectors.reshape(self.index.ntotal, self.EMBEDDING_DIM).copy()
            keep_mask = [i for i in range(self.index.ntotal) if i != index_pos]
            new_index = faiss.IndexFlatIP(self.EMBEDDING_DIM)
            new_map: dict[int, str] = {}
            if keep_mask:
                kept = all_vectors[keep_mask]
                new_index.add(kept)
                for new_i, old_i in enumerate(keep_mask):
                    if old_i in self._embedding_map:
                        new_map[new_i] = self._embedding_map[old_i]
            self.index = new_index
            self._embedding_map = new_map

    def rollback_last_add(self) -> None:
        """Remove last added vector after failed DB write."""
        with self._lock:
            if self.index.ntotal == 0:
                return
            last_pos = self.index.ntotal - 1
            self.remove_by_index(last_pos)
