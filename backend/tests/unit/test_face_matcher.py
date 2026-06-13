"""FAISS matcher unit tests."""

import numpy as np
import pytest

from backend.core.face_matcher import FaceMatcher


def test_add_search_save_load(tmp_path):
    matcher = FaceMatcher()
    matcher.index_path = tmp_path / "idx.bin"
    matcher.map_path = tmp_path / "map.json"

    emb = np.random.randn(512).astype(np.float32)
    pos = matcher.add(emb)
    assert pos == 0
    matcher.set_participant_id(0, "user-1")

    sim, idx = matcher.search(emb)
    assert idx == 0
    assert sim > 0.99

    matcher.save()
    matcher2 = FaceMatcher()
    matcher2.index_path = tmp_path / "idx.bin"
    matcher2.map_path = tmp_path / "map.json"
    matcher2.load()
    assert matcher2.count() == 1
    assert matcher2.get_participant_id(0) == "user-1"


def test_thread_safe_add(tmp_path):
    import threading

    matcher = FaceMatcher()
    matcher.index_path = tmp_path / "idx.bin"
    matcher.map_path = tmp_path / "map.json"

    def worker():
        for _ in range(5):
            e = np.random.randn(512).astype(np.float32)
            matcher.add(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert matcher.count() == 20
