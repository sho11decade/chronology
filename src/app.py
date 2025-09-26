from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

# Add current directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from .models import (
        GenerateRequest,
        GenerateResponse,
        HistoryResponse,
        TimelineSummary,
        UploadResponse,
    )
    from .text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from .timeline_generator import generate_timeline
    from .database import (
        init_db,
        store_timeline,
        fetch_recent_timelines,
        fetch_timeline,
    )
except ImportError:
    # Fallback to absolute imports when running as script
    from models import (
        GenerateRequest,
        GenerateResponse,
        HistoryResponse,
        TimelineSummary,
        UploadResponse,
    )
    from text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from timeline_generator import generate_timeline
    from database import init_db, store_timeline, fetch_recent_timelines, fetch_timeline


DB_PATH = Path(os.getenv("CHRONOLOGY_DB_PATH", current_dir / "chronology.db"))


app = FastAPI(
    title="Chronology Maker API",
    description="テキストから年表を生成するためのAPI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await run_in_threadpool(init_db, DB_PATH)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    text, preview = await extract_text_from_upload(file)
    return UploadResponse(
        filename=file.filename or "uploaded",
        characters=len(text),
        text_preview=preview,
        text=text,
    )


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    if len(request.text) > MAX_CHARACTERS:
        raise HTTPException(status_code=400, detail="文字数が制限を超えています (最大50,000文字)")

    items = generate_timeline(request.text)
    request_id = await run_in_threadpool(
        store_timeline,
        request.text,
        items,
        source="api",
        db_path=DB_PATH,
    )

    return GenerateResponse(
        request_id=request_id,
        items=items,
        total_events=len(items),
        generated_at=datetime.utcnow(),
    )


@app.get("/api/history", response_model=HistoryResponse)
async def history(limit: int = 10) -> HistoryResponse:
    limit = max(1, min(limit, 50))
    rows = await run_in_threadpool(fetch_recent_timelines, limit, db_path=DB_PATH)
    summaries = [
        TimelineSummary(
            request_id=row[0],
            generated_at=row[1],
            total_events=row[2],
            text_preview=row[3],
        )
        for row in rows
    ]
    return HistoryResponse(timelines=summaries)


@app.get("/api/history/{request_id}", response_model=GenerateResponse)
async def history_detail(request_id: int) -> GenerateResponse:
    generated_at, items = await run_in_threadpool(
        fetch_timeline,
        request_id,
        db_path=DB_PATH,
    )
    if generated_at is None:
        raise HTTPException(status_code=404, detail="指定された年表が見つかりませんでした。")

    return GenerateResponse(
        request_id=request_id,
        items=items,
        total_events=len(items),
        generated_at=generated_at,
    )
