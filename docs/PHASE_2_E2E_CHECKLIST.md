# Phase 2 E2E Checklist

Manual validation on GCP VM after Phase 2 deployment.

## Prerequisites

- Phase 1 health checks passing
- DEIMv2 ONNX at `models/deimv2_s_wholebody49.onnx`
- Test video in `test_data/` (`./scripts/fetch_test_video.sh <url>`)
- Register **at least 5 faces** from test video (Phase 3 prep)

## Stack

```bash
docker compose up -d --build
# CPU-only interim VM:
# docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

## Automated verification

```bash
# Prerequisites only
python scripts/verify_phase2_e2e.py --check-only

# Full Redis/runtime checks (docker workers must be running)
python scripts/verify_phase2_e2e.py --full --start-stream --video test_data/test.mp4
```

## Integration tests (on VM)

```bash
export RUN_INTEGRATION_TESTS=1
export DEIMv2_INTEGRATION=1
export JWT_SECRET=your-jwt-secret-min-32-chars
export REDIS_URL=redis://localhost:6379/0
export DB_PASSWORD=your-db-password
export WORKER_DATABASE_URL=postgresql://spatialscore:$DB_PASSWORD@localhost:5432/spatialscore

pytest backend/tests/integration/test_camera_pipeline.py -v -m integration
pytest backend/tests/integration/test_identity_pipeline.py -v -m integration
```

## Stream simulation

```bash
python scripts/simulate_streams.py --video test_data/test.mp4 --camera-id cam01 --host 127.0.0.1 &
python scripts/simulate_streams.py --video test_data/test.mp4 --camera-id cam02 --host 127.0.0.1 &
```

## Verify Redis

```bash
redis-cli XLEN activity_stream
redis-cli XREAD COUNT 3 STREAMS activity_stream 0
redis-cli HGETALL zone_occupancy
redis-cli HGETALL camera_status:CAM-01
redis-cli TTL camera_frame:CAM-01
```

## Verify API

```bash
curl -s http://localhost:8000/api/v1/health | jq .
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/metrics | jq .
```

## Visual checks

- [ ] DetectionsSmoother: track boxes stable on test video (logs + decoded frames)
- [ ] Annotated frame colors: coding green, collaborating blue, mentoring orange
- [ ] Unknown tracks counted in `zone_occupancy` but no events without `participant_id`
- [ ] Event `confidence` matches FAISS similarity in worker logs
- [ ] Interrupt RTSP: heartbeat `status` goes `reconnecting` then `active`

## Decode camera frame from Redis

```python
import redis
r = redis.Redis(decode_responses=False)
data = r.get("camera_frame:CAM-01")
open("/tmp/frame.jpg", "wb").write(data)
```

## VRAM (GPU VM)

```bash
nvidia-smi  # two workers should stay under 4GB combined for dev test
```
