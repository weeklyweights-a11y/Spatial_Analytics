# Browser E2E Checklist (Phase 1)

Manual verification on GCP VM or local Docker before the event. Not automated in CI.

## Prerequisites

- [ ] `docker compose up` — all services running
- [ ] Models downloaded (`./scripts/download_models.sh`)
- [ ] Admin user created (`python -m backend.cli create-user ...`)
- [ ] Browser with camera access (tablet or laptop)

## Login flow

- [ ] Open http://localhost:3000
- [ ] Login page displays
- [ ] Valid credentials redirect to CCTV Wall with sidebar
- [ ] Invalid credentials show error

## Registration flow

- [ ] Navigate to Registration (operator/admin only)
- [ ] Camera preview starts
- [ ] Capture freezes frame
- [ ] Fill name, team, track, skills, consent
- [ ] Submit creates participant — success message with count
- [ ] Counter updates in corner
- [ ] Form resets for next participant
- [ ] Staff verifies physical ID before capture (process check)

## Error states

- [ ] No face / bad photo shows error
- [ ] Duplicate face shows "Already registered"
- [ ] Missing required fields shows "Missing fields"

## Persistence

- [ ] Restart `api` container — participants still listed
- [ ] FAISS embeddings survive restart
