from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.agent import apply_adjustment, build_travel_plan
from app.chat_parser import parse_chat_message
from app.schemas import AdjustmentRequest, ChatRequest, PlanResponse, TravelRequest, UploadResponse
from app.storage import EXPORT_DIR, ROOT, ingest_file, read_memory

load_dotenv(ROOT / ".env", override=True)

app = FastAPI(title="TravelMate Agent", description="旅行伙计 AI 多工具调用旅行规划智能体", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "deepseek_enabled": bool(os.getenv("DEEPSEEK_API_KEY")),
        "features": ["weather", "attractions", "guide_cleaning", "transport", "budget", "rag_upload", "markdown_export"],
    }


@app.get("/api/memory")
async def memory() -> dict:
    return read_memory()


@app.post("/api/plan", response_model=PlanResponse)
async def plan(request: TravelRequest) -> PlanResponse:
    return await build_travel_plan(request)


@app.post("/api/chat-plan", response_model=PlanResponse)
async def chat_plan(request: ChatRequest) -> PlanResponse:
    parsed = parse_chat_message(request.message)
    return await build_travel_plan(parsed)


@app.post("/api/adjust-plan", response_model=PlanResponse)
async def adjust_plan(request: AdjustmentRequest) -> PlanResponse:
    adjusted = apply_adjustment(request.base_request, request.instruction)
    return await build_travel_plan(adjusted)


@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".md", ".pdf"}:
        raise HTTPException(status_code=400, detail="仅支持 PDF/TXT/Markdown 攻略上传")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大，Demo 限制为 8MB")
    result = ingest_file(file.filename or "guide.txt", content)
    return UploadResponse(**result, message="已写入本地轻量 RAG 知识库，后续规划会自动检索。")


@app.get("/exports/{filename}")
async def export_file(filename: str) -> FileResponse:
    path = (EXPORT_DIR / filename).resolve()
    if not str(path).startswith(str(EXPORT_DIR.resolve())) or not path.exists():
        raise HTTPException(status_code=404, detail="导出文件不存在")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=filename)
