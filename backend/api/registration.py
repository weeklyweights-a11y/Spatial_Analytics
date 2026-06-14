"""Face registration endpoint."""

import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, get_face_matcher, require_role
from backend.api.schemas import VALID_TRACKS, ParticipantResponse
from backend.config import get_settings
from backend.core.face_detector import FaceDetector
from backend.core.face_recognizer import FaceRecognizer
from backend.db.database import get_db
from backend.db.models import Participant, Score
from backend.middleware.rate_limit import limiter
from backend.utils.files import decode_image

router = APIRouter(prefix="/api/v1", tags=["registration"])
settings = get_settings()


def _get_detector(request: Request) -> FaceDetector:
    detector = request.app.state.face_detector
    if detector is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Face models not loaded", "code": "MODELS_UNAVAILABLE"},
        )
    return detector


def _get_recognizer(request: Request) -> FaceRecognizer:
    recognizer = request.app.state.face_recognizer
    if recognizer is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Face models not loaded", "code": "MODELS_UNAVAILABLE"},
        )
    return recognizer


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register_participant(
    request: Request,
    photo: UploadFile = File(...),
    name: str = Form(...),
    team_name: str = Form(...),
    track: str = Form(...),
    consent_confirmed: bool = Form(...),
    email: Optional[str] = Form(None),
    skills: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
    face_matcher=Depends(get_face_matcher),
    detector: FaceDetector = Depends(_get_detector),
    recognizer: FaceRecognizer = Depends(_get_recognizer),
) -> dict:
    """Register participant with face capture."""
    if not consent_confirmed:
        raise HTTPException(
            status_code=422,
            detail={"error": "Consent must be confirmed", "code": "CONSENT_REQUIRED"},
        )
    if track not in VALID_TRACKS:
        raise HTTPException(
            status_code=422,
            detail={"error": f"Invalid track. Must be one of: {', '.join(sorted(VALID_TRACKS))}", "code": "INVALID_TRACK"},
        )

    raw = await photo.read()
    try:
        image = decode_image(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": str(exc), "code": "INVALID_IMAGE"},
        ) from exc

    faces = detector.detect(image)
    if len(faces) == 0:
        logger.warning("No face detected in registration photo")
        raise HTTPException(
            status_code=400,
            detail={"error": "No face detected in photo", "code": "NO_FACE"},
        )
    if len(faces) > 1:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Multiple faces detected, please capture one person at a time",
                "code": "MULTIPLE_FACES",
            },
        )

    face = faces[0]
    aligned = recognizer.align_face(image, face.landmarks)
    embedding = recognizer.embed(aligned)

    sim, idx = face_matcher.search(embedding, k=1)
    if sim > settings.DUPLICATE_REGISTRATION_THRESHOLD and idx >= 0:
        existing_id = face_matcher.get_participant_id(idx)
        existing_name = "Unknown"
        if existing_id:
            result = await db.execute(select(Participant).where(Participant.id == uuid.UUID(existing_id)))
            existing = result.scalar_one_or_none()
            if existing:
                existing_name = existing.name
        logger.warning("Duplicate face detected: similarity={sim}, existing={name}", sim=sim, name=existing_name)
        raise HTTPException(
            status_code=409,
            detail={"error": f"Already registered as {existing_name}", "code": "DUPLICATE_FACE"},
        )

    participant_id = uuid.uuid4()
    index_pos = face_matcher.add(embedding)
    face_matcher.set_participant_id(index_pos, str(participant_id))

    photo_dir = Path(settings.EMBEDDING_MAP_PATH).parent.parent / "faces"
    photo_dir.mkdir(parents=True, exist_ok=True)
    photo_path = photo_dir / f"{participant_id}.jpg"
    try:
        import cv2

        cv2.imwrite(str(photo_path), image)

        skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else None
        participant = Participant(
            id=participant_id,
            name=name,
            email=email or None,
            team_name=team_name,
            track=track,
            skills=skills_list,
            photo_path=str(photo_path),
            embedding_id=index_pos,
        )
        db.add(participant)
        db.add(Score(participant_id=participant_id))
        await db.flush()
        face_matcher.save()
    except Exception as exc:
        face_matcher.rollback_last_add()
        logger.error("Database connection failed: {error}", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={"error": "Registration failed", "code": "INTERNAL_ERROR"},
        ) from exc

    logger.info(
        "Registration: {name}, team={team}, embedding_id={id}",
        name=name,
        team=team_name,
        id=index_pos,
    )

    response = ParticipantResponse.model_validate(participant)
    return {"data": response.model_dump()}
