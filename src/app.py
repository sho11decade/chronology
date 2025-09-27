from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

# Add current directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from .settings import settings
    from .models import (
        GenerateRequest,
        GenerateResponse,
        HistoryResponse,
        TimelineSummary,
        UploadResponse,
    )
    from .models import WikipediaImportRequest, WikipediaImportResponse
    from .text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from .timeline_generator import generate_timeline
    from .database import (
        init_db,
        store_timeline,
        fetch_recent_timelines,
        fetch_timeline,
        check_database_ready,
    )
    from .wikipedia_importer import fetch_wikipedia_article
except ImportError:
    # Fallback to absolute imports when running as script
    from settings import settings
    from models import (
        GenerateRequest,
        GenerateResponse,
        HistoryResponse,
        TimelineSummary,
        UploadResponse,
    )
    from models import WikipediaImportRequest, WikipediaImportResponse
    from text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from timeline_generator import generate_timeline
    from database import (
        init_db,
        store_timeline,
        fetch_recent_timelines,
        fetch_timeline,
        check_database_ready,
    )
    from wikipedia_importer import fetch_wikipedia_article


LOG_LEVEL = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("chronology.app")
logger.setLevel(LOG_LEVEL)

DB_PATH = Path(settings.chronology_db_path)
ALLOWED_ORIGINS = settings.allowed_origins or ["*"]


app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _uptime_seconds() -> float:
    started_at = getattr(app.state, "started_at", None)
    if not started_at:
        return 0.0
    return max(0.0, (datetime.utcnow() - started_at).total_seconds())


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    if settings.enable_request_logging:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    logger.exception(
        "Unhandled server error",
        extra={"request_id": request_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "サーバー内部で予期しないエラーが発生しました。",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


@app.on_event("startup")
async def startup() -> None:
    app.state.started_at = datetime.utcnow()
    app.state.settings = settings
    await run_in_threadpool(init_db, DB_PATH)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "uptime_seconds": round(_uptime_seconds(), 3),
        "version": app.version,
    }


@app.get("/health/live")
async def health_live() -> Dict[str, Any]:
    return {"status": "ok", "uptime_seconds": round(_uptime_seconds(), 3)}


@app.get("/health/ready")
async def health_ready(request: Request) -> Dict[str, Any]:
    try:
        await run_in_threadpool(check_database_ready, db_path=DB_PATH)
    except Exception as exc:  # pragma: no cover - defensive guard
        request_id = getattr(request.state, "request_id", str(uuid4()))
        logger.exception(
            "Database readiness check failed",
            extra={"request_id": request_id},
        )
        headers = {"X-Request-ID": request_id}
        raise HTTPException(
            status_code=503,
            detail="データベースに接続できません。",
            headers=headers,
        ) from exc
    return {"status": "ok", "uptime_seconds": round(_uptime_seconds(), 3)}


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


@app.post("/api/import/wikipedia", response_model=WikipediaImportResponse)
async def import_wikipedia(request: WikipediaImportRequest) -> WikipediaImportResponse:
    article = await run_in_threadpool(
        fetch_wikipedia_article,
        topic=request.topic,
        url=str(request.url) if request.url else None,
        language=request.language,
    )

    items = generate_timeline(article.text)
    request_id = await run_in_threadpool(
        store_timeline,
        article.text,
        items,
        source=f"wikipedia:{article.language}",
        db_path=DB_PATH,
    )

    return WikipediaImportResponse(
        source_title=article.title,
        source_url=article.url,
        characters=article.characters,
        text_preview=article.preview,
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
