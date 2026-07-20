from __future__ import annotations

import json
import re
import time
from pathlib import Path

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional in dev environments
    PdfReader = None


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
MEMORY_DIR = DATA_DIR / "memory"

for directory in (UPLOAD_DIR, EXPORT_DIR, MEMORY_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def read_memory(user_id: str = "local") -> dict:
    path = MEMORY_DIR / f"{safe_name(user_id)}.json"
    if not path.exists():
        return {"origin": "", "interests": [], "constraints": [], "recent_destinations": []}
    return json.loads(path.read_text(encoding="utf-8"))


def update_memory(patch: dict, user_id: str = "local") -> dict:
    memory = read_memory(user_id)
    for key, value in patch.items():
        if not value:
            continue
        if isinstance(value, list):
            memory[key] = list(dict.fromkeys([*(memory.get(key) or []), *value]))[:20]
        elif key == "recent_destinations":
            memory[key] = list(dict.fromkeys([value, *(memory.get(key) or [])]))[:10]
        else:
            memory[key] = value
    path = MEMORY_DIR / f"{safe_name(user_id)}.json"
    path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    return memory


def ingest_file(filename: str, content: bytes) -> dict:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    clean_filename = f"{int(time.time())}-{safe_name(filename)}"
    path = UPLOAD_DIR / clean_filename
    path.write_bytes(content)
    text = extract_text(path)
    chunks = chunk_text(text)
    index_path = UPLOAD_DIR / f"{clean_filename}.json"
    index_path.write_text(
        json.dumps({"filename": filename, "path": str(path), "chunks": chunks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"filename": filename, "characters": len(text), "chunks": len(chunks)}


def search_private_knowledge(query: str, limit: int = 4) -> list[str]:
    query_terms = tokenize(query)
    if not query_terms:
        return []
    matches: list[tuple[int, str]] = []
    for index_file in UPLOAD_DIR.glob("*.json"):
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for chunk in data.get("chunks", []):
            score = sum(1 for term in query_terms if term in chunk)
            if score:
                matches.append((score, f"{data.get('filename', '私有攻略')}：{chunk[:220]}"))
    matches.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in matches[:limit]]


def write_export(plan_id: str, markdown: str) -> str:
    path = EXPORT_DIR / f"{safe_name(plan_id)}.md"
    path.write_text(markdown, encoding="utf-8")
    return f"/exports/{path.name}"


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf" and PdfReader is not None:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def chunk_text(text: str, size: int = 450, overlap: int = 80) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    chunks = []
    start = 0
    while start < len(normalized):
        chunks.append(normalized[start : start + size])
        start += max(size - overlap, 1)
    return chunks


def tokenize(text: str) -> list[str]:
    raw = re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9]{2,}", text.lower())
    stop = {"旅行", "攻略", "景点", "推荐", "城市", "预算"}
    return [item for item in raw if item not in stop]


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fa5.-]+", "-", value, flags=re.UNICODE).strip("-")
    return cleaned[:80] or "file"
