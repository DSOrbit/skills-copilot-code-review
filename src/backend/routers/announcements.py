"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from uuid import uuid4
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    expiration_date: str
    start_date: Optional[str] = None


class AnnouncementResponse(BaseModel):
    id: str
    message: str
    expiration_date: str
    start_date: Optional[str] = None


def _validate_date_or_none(date_value: Optional[str], field_name: str) -> Optional[str]:
    if date_value in (None, ""):
        return None

    try:
        date.fromisoformat(date_value)
        return date_value
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}. Use YYYY-MM-DD format")


def _validate_announcement_dates(start_date: Optional[str], expiration_date: str) -> Dict[str, Optional[str]]:
    validated_start = _validate_date_or_none(start_date, "start_date")
    validated_expiration = _validate_date_or_none(expiration_date, "expiration_date")

    if validated_expiration is None:
        raise HTTPException(status_code=400, detail="expiration_date is required")

    if validated_start and validated_start > validated_expiration:
        raise HTTPException(status_code=400, detail="start_date cannot be after expiration_date")

    return {
        "start_date": validated_start,
        "expiration_date": validated_expiration
    }


def _require_signed_in_user(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _map_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": document.get("_id"),
        "message": document.get("message", ""),
        "start_date": document.get("start_date"),
        "expiration_date": document.get("expiration_date")
    }


@router.get("/active", response_model=List[AnnouncementResponse])
def get_active_announcements() -> List[AnnouncementResponse]:
    """Get all currently active announcements for public display"""
    today = date.today().isoformat()

    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": {"$exists": False}},
            {"start_date": None},
            {"start_date": ""},
            {"start_date": {"$lte": today}}
        ]
    }

    announcements = [
        _map_announcement(document)
        for document in announcements_collection.find(query).sort("expiration_date", 1)
    ]

    return announcements


@router.get("", response_model=List[AnnouncementResponse])
@router.get("/", response_model=List[AnnouncementResponse])
def list_announcements(teacher_username: Optional[str] = Query(None)) -> List[AnnouncementResponse]:
    """List all announcements for management (requires authentication)"""
    _require_signed_in_user(teacher_username)

    return [
        _map_announcement(document)
        for document in announcements_collection.find().sort("expiration_date", 1)
    ]


@router.post("", response_model=AnnouncementResponse)
@router.post("/", response_model=AnnouncementResponse)
def create_announcement(payload: AnnouncementPayload, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Create a new announcement (requires authentication)"""
    _require_signed_in_user(teacher_username)
    dates = _validate_announcement_dates(payload.start_date, payload.expiration_date)

    new_document = {
        "_id": str(uuid4()),
        "message": payload.message.strip(),
        "start_date": dates["start_date"],
        "expiration_date": dates["expiration_date"]
    }

    announcements_collection.insert_one(new_document)
    return _map_announcement(new_document)


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement (requires authentication)"""
    _require_signed_in_user(teacher_username)
    dates = _validate_announcement_dates(payload.start_date, payload.expiration_date)

    update_fields = {
        "message": payload.message.strip(),
        "start_date": dates["start_date"],
        "expiration_date": dates["expiration_date"]
    }

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": update_fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated_document = announcements_collection.find_one({"_id": announcement_id})
    return _map_announcement(updated_document)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Delete an announcement (requires authentication)"""
    _require_signed_in_user(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
