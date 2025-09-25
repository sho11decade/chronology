from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# Add current directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from .models import GenerateRequest, GenerateResponse, UploadResponse
    from .text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from .timeline_generator import generate_timeline
except ImportError:
    # Fallback to absolute imports when running as script
    from models import GenerateRequest, GenerateResponse, UploadResponse
    from text_extractor import extract_text_from_upload, MAX_CHARACTERS
    from timeline_generator import generate_timeline


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
    return GenerateResponse(
        items=items,
        total_events=len(items),
        generated_at=datetime.utcnow(),
    )
