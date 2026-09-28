"""Public website routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.services.storage import LocalStorage, get_storage, is_safe_key
from app.templating import render

router = APIRouter()
settings = get_settings()


@router.get("/")
async def home(request: Request):
    return render(request, "public/home.html")


@router.get("/zdravlje")
async def health(db: Session = Depends(get_db)):
    """Health check for Docker/monitoring. Deliberately reveals no versions or details."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB error means unhealthy
        return JSONResponse({"status": "error", "db": "error"}, status_code=503)
    return {"status": "ok", "db": "ok"}


@router.get("/media/{key:path}")
async def media(key: str):
    """Serve locally stored media. Only generated `.webp` files, no path traversal."""
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not key.endswith(".webp") or not is_safe_key(key):
        raise HTTPException(status_code=404)
    try:
        path = storage._path(key)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/webp")
