#!/usr/bin/env python3
import onnxruntime as ort
from backend.config import get_settings

path = str(get_settings().deimv2_model_path)
s = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
print("inputs:", [(i.name, i.shape, i.type) for i in s.get_inputs()])
print("outputs:", [(o.name, o.shape, o.type) for o in s.get_outputs()])
