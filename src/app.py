from __future__ import annotations

import logging
import sys
import time
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
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
        SearchRequest,
        SearchResponse,
        UploadResponse,
    )
    from .models import WikipediaImportRequest, WikipediaImportResponse
    from .text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from .timeline_generator import generate_timeline
    from .search import search_timeline_items
    from .wikipedia_importer import fetch_wikipedia_article
    from .models import (
        ShareCreateRequest,
        ShareCreateResponse,
        ShareGetResponse,
        SharePublicResponse,
    )
    from .share_store import ShareStore, D1Config
except ImportError:
    # Fallback to absolute imports when running as script
    from settings import settings
    from models import (
        GenerateRequest,
        GenerateResponse,
        SearchRequest,
        SearchResponse,
        UploadResponse,
    )
    from models import WikipediaImportRequest, WikipediaImportResponse
    from text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from timeline_generator import generate_timeline
    from search import search_timeline_items
    from wikipedia_importer import fetch_wikipedia_article
    from models import (
        ShareCreateRequest,
        ShareCreateResponse,
        ShareGetResponse,
        SharePublicResponse,
    )
    from share_store import ShareStore, D1Config


LOG_LEVEL = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("chronology.app")
logger.setLevel(LOG_LEVEL)

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
    # 共有ストア初期化
    d1_cfg = D1Config(
        enabled=bool(getattr(settings, "d1_enabled", False)),
        account_id=getattr(settings, "d1_account_id", ""),
        database_id=getattr(settings, "d1_database_id", ""),
        api_token=getattr(settings, "d1_api_token", ""),
    )
    # テスト実行時はD1を強制無効化（外部依存を避ける）
    if os.environ.get("PYTEST_CURRENT_TEST"):
        d1_cfg.enabled = False
    app.state.share_store = ShareStore(d1=d1_cfg)


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
async def health_ready() -> Dict[str, Any]:
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

    return GenerateResponse(
        items=items,
        total_events=len(items),
        generated_at=datetime.utcnow(),
    )


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    items = generate_timeline(request.text)
    results = search_timeline_items(
        items,
        keywords=request.keywords,
        categories=request.categories,
        date_from=request.date_from,
        date_to=request.date_to,
        match_mode=request.match_mode,
        max_results=request.max_results,
    )

    return SearchResponse(
        keywords=request.keywords,
        categories=request.categories,
        date_from=request.date_from,
        date_to=request.date_to,
        match_mode=request.match_mode,
        total_events=len(items),
        total_matches=len(results),
        results=results,
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

    return WikipediaImportResponse(
        source_title=article.title,
        source_url=article.url,
        characters=article.characters,
        text_preview=article.preview,
        items=items,
        total_events=len(items),
        generated_at=datetime.utcnow(),
    )


@app.post("/api/share", response_model=ShareCreateResponse)
async def create_share(request: ShareCreateRequest) -> ShareCreateResponse:
    if not settings.enable_sharing:
        raise HTTPException(status_code=403, detail="共有機能は無効化されています。")
    if len(request.text) > MAX_CHARACTERS:
        raise HTTPException(status_code=400, detail="文字数が制限を超えています (最大50,000文字)")

    items = generate_timeline(request.text)
    store: ShareStore = app.state.share_store
    # 有効期限
    ttl_days = int(getattr(settings, "share_ttl_days", 30) or 30)
    expires_at_dt = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    expires_at_iso = expires_at_dt.isoformat()

    share_id, created_at_iso, expires_at_iso_out = store.create_share(
        text=request.text,
        title=request.title or "",
        items=[item.dict() for item in items],
        expires_at_iso=expires_at_iso,
    )

    base = (settings.public_base_url or "").rstrip("/")
    path = f"/share/{share_id}"
    url = f"{base}{path}" if base else path

    return ShareCreateResponse(
        id=share_id,
        url=url,
        created_at=datetime.fromisoformat(created_at_iso),
        total_events=len(items),
        expires_at=datetime.fromisoformat(expires_at_iso_out),
    )


@app.get("/api/share/{share_id}", response_model=ShareGetResponse)
async def get_share(share_id: str) -> ShareGetResponse:
    if not settings.enable_sharing:
        raise HTTPException(status_code=403, detail="共有機能は無効化されています。")
    store: ShareStore = app.state.share_store
    rec = store.get_share(share_id)
    if not rec:
        raise HTTPException(status_code=404, detail="共有が見つかりませんでした。")
    # 期限切れ判定
    try:
        exp = datetime.fromisoformat(rec["expires_at"]).astimezone(timezone.utc)
    except Exception:
        exp = datetime.now(timezone.utc)  # 異常値は期限切れ扱い
    if datetime.now(timezone.utc) > exp:
        raise HTTPException(status_code=404, detail="共有の有効期限が切れています。")
    return ShareGetResponse(
        id=rec["id"],
        title=rec["title"],
        text=rec["text"],
        items=[item for item in rec["items"]],
        created_at=datetime.fromisoformat(rec["created_at"]),
        expires_at=exp,
    )


def _share_etag(share_id: str, created_at_iso: str) -> str:
    # 弱いETagで十分
    return f'W/"{share_id}-{created_at_iso}"'


@app.get("/api/share/{share_id}/items", response_model=SharePublicResponse)
async def get_share_public(share_id: str, request: Request) -> JSONResponse:
    """公開用：本文を含まず items のみ返す。キャッシュヘッダを付与。"""
    if not settings.enable_sharing:
        raise HTTPException(status_code=403, detail="共有機能は無効化されています。")
    store: ShareStore = app.state.share_store
    rec = store.get_share(share_id)
    if not rec:
        raise HTTPException(status_code=404, detail="共有が見つかりませんでした。")
    # 期限切れ
    try:
        exp = datetime.fromisoformat(rec["expires_at"]).astimezone(timezone.utc)
    except Exception:
        exp = datetime.now(timezone.utc)
    if datetime.now(timezone.utc) > exp:
        raise HTTPException(status_code=404, detail="共有の有効期限が切れています。")

    created_at_iso = rec["created_at"]
    etag = _share_etag(share_id, created_at_iso)

    # If-None-Match 処理
    inm = request.headers.get("If-None-Match")
    if inm and inm == etag:
        return JSONResponse(status_code=304, content=None, headers={"ETag": etag})

    payload = SharePublicResponse(
        id=rec["id"],
        title=rec["title"],
        items=[item for item in rec["items"]],
        created_at=datetime.fromisoformat(created_at_iso),
        expires_at=exp,
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(payload),
        headers={
            "Cache-Control": "public, max-age=300",
            "ETag": etag,
        },
    )


@app.get("/api/share/{share_id}/export")
async def export_share_json(share_id: str) -> JSONResponse:
    """ダウンロード用：全文（text + items）をJSONとして添付返却。"""
    if not settings.enable_sharing:
        raise HTTPException(status_code=403, detail="共有機能は無効化されています。")
    store: ShareStore = app.state.share_store
    rec = store.get_share(share_id)
    if not rec:
        raise HTTPException(status_code=404, detail="共有が見つかりませんでした。")
    try:
        exp = datetime.fromisoformat(rec["expires_at"]).astimezone(timezone.utc)
    except Exception:
        exp = datetime.now(timezone.utc)
    if datetime.now(timezone.utc) > exp:
        raise HTTPException(status_code=404, detail="共有の有効期限が切れています。")

    content = {
        "id": rec["id"],
        "title": rec["title"],
        "text": rec["text"],
        "items": rec["items"],
        "created_at": rec["created_at"],
        "expires_at": rec["expires_at"],
    }
    headers = {
        "Content-Disposition": f'attachment; filename="timeline-{share_id}.json"'
    }
    return JSONResponse(status_code=200, content=content, headers=headers)
