"""Knowledge base API — upload, list, delete PDFs for RAG."""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.knowledge_manager import upload_pdf, list_documents, delete_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploaded_pdfs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_knowledge_pdf(
    file: UploadFile = File(...),
    category: str = Form("general"),
):
    """Upload a PDF, extract text, chunk, embed, and store in ChromaDB."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    # Save file to disk
    dest = UPLOAD_DIR / file.filename
    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {e}")

    # Process
    try:
        result = await upload_pdf(str(dest), category=category)
        return {"status": "ok", **result}
    except Exception as e:
        logger.exception("PDF upload processing failed")
        raise HTTPException(status_code=500, detail=f"PDF 처리 실패: {e}")


@router.get("/list")
def list_knowledge():
    """List all uploaded knowledge documents."""
    try:
        docs = list_documents()
        return {"documents": docs, "total": len(docs)}
    except Exception as e:
        logger.exception("Failed to list documents")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{doc_id}")
def delete_knowledge(doc_id: str):
    """Delete a document and its chunks from ChromaDB."""
    try:
        result = delete_document(doc_id)
        return {"status": "ok", **result}
    except Exception as e:
        logger.exception("Failed to delete document")
        raise HTTPException(status_code=500, detail=str(e))
