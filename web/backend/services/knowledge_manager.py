"""PDF processing pipeline — parse, chunk, embed, store in ChromaDB."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

import chromadb
import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter

from services.llm import get_provider

logger = logging.getLogger(__name__)

KNOWLEDGE_DB_DIR = Path(__file__).resolve().parent.parent / "knowledge_db"
COLLECTION_NAME = "apartment_knowledge"

_client: Optional[chromadb.PersistentClient] = None


def _get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        KNOWLEDGE_DB_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(KNOWLEDGE_DB_DIR))
    return _client


def get_collection() -> chromadb.Collection:
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _embed_sync(text: str) -> list[float]:
    """Synchronously generate an embedding using the LLM provider."""
    provider = get_provider()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context — use a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, provider.embed(text))
            return future.result()
    else:
        return asyncio.run(provider.embed(text))


def _extract_text_from_pdf(file_path: str) -> list[dict[str, Any]]:
    """Extract text from a PDF, returning a list of {page_number, text}."""
    doc = fitz.open(file_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        if text.strip():
            pages.append({"page_number": page_num + 1, "text": text})
    doc.close()
    return pages


def _chunk_pages(
    pages: list[dict[str, Any]],
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> list[dict[str, Any]]:
    """Split page texts into smaller chunks with metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    chunks = []
    chunk_index = 0
    for page_info in pages:
        texts = splitter.split_text(page_info["text"])
        for t in texts:
            chunks.append({
                "text": t,
                "page_number": page_info["page_number"],
                "chunk_index": chunk_index,
            })
            chunk_index += 1
    return chunks


async def upload_pdf(file_path: str, category: str = "general") -> dict[str, Any]:
    """Parse PDF, chunk, embed, and store in ChromaDB.

    Returns metadata about the uploaded document.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    doc_id = uuid.uuid4().hex[:12]
    filename = path.name

    # 1. Extract text
    pages = _extract_text_from_pdf(file_path)
    if not pages:
        raise ValueError("PDF contains no extractable text.")

    # 2. Chunk
    chunks = _chunk_pages(pages)
    logger.info(f"PDF '{filename}' -> {len(pages)} pages, {len(chunks)} chunks")

    # 3. Embed
    provider = get_provider()
    embeddings: list[list[float]] = []
    for chunk in chunks:
        emb = await provider.embed(chunk["text"])
        embeddings.append(emb)

    # 4. Store in ChromaDB
    collection = get_collection()
    ids = [f"{doc_id}_chunk_{c['chunk_index']}" for c in chunks]
    metadatas = [
        {
            "doc_id": doc_id,
            "filename": filename,
            "category": category,
            "page_number": c["page_number"],
            "chunk_index": c["chunk_index"],
        }
        for c in chunks
    ]
    documents = [c["text"] for c in chunks]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents,
    )

    return {
        "doc_id": doc_id,
        "filename": filename,
        "category": category,
        "pages": len(pages),
        "chunks": len(chunks),
    }


def list_documents() -> list[dict[str, Any]]:
    """List all uploaded documents with metadata."""
    collection = get_collection()
    result = collection.get(include=["metadatas"])

    if not result["metadatas"]:
        return []

    # Group by doc_id
    docs: dict[str, dict] = {}
    for meta in result["metadatas"]:
        did = meta["doc_id"]
        if did not in docs:
            docs[did] = {
                "doc_id": did,
                "filename": meta["filename"],
                "category": meta.get("category", "general"),
                "chunks": 0,
            }
        docs[did]["chunks"] += 1

    return list(docs.values())


def delete_document(doc_id: str) -> dict[str, Any]:
    """Remove all chunks for a document from ChromaDB."""
    collection = get_collection()

    # Find all chunk IDs for this doc_id
    result = collection.get(
        where={"doc_id": doc_id},
        include=["metadatas"],
    )

    if not result["ids"]:
        return {"deleted": 0, "message": f"No document found with id '{doc_id}'."}

    collection.delete(ids=result["ids"])
    return {"deleted": len(result["ids"]), "doc_id": doc_id}
