"""RAG pipeline — retrieve relevant chunks from ChromaDB and generate answers."""

import logging
from typing import Any

from services.llm import get_provider
from services.knowledge_manager import get_collection

logger = logging.getLogger(__name__)


async def search_knowledge_rag(query: str, k: int = 5) -> dict[str, Any]:
    """Search ChromaDB for relevant documents and return passages with sources.

    Args:
        query: The search query.
        k: Number of results to return.

    Returns:
        dict with "passages" (list of text+source) and "answer" placeholder.
    """
    collection = get_collection()

    # Check if collection has any documents
    if collection.count() == 0:
        return {
            "answer": "",
            "passages": [],
            "sources": [],
            "message": "업로드된 지식 문서가 없습니다. PDF를 먼저 업로드해주세요.",
        }

    # 1. Embed query
    provider = get_provider()
    try:
        query_embedding = await provider.embed(query)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        # Fallback: use ChromaDB's default text-based query
        results = collection.query(query_texts=[query], n_results=k, include=["documents", "metadatas", "distances"])
        return _format_results(results)

    # 2. Similarity search
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    return _format_results(results)


def _format_results(results: dict) -> dict[str, Any]:
    """Format ChromaDB query results into a structured response."""
    if not results["documents"] or not results["documents"][0]:
        return {
            "answer": "",
            "passages": [],
            "sources": [],
            "message": "관련 문서를 찾을 수 없습니다.",
        }

    passages = []
    sources = []
    seen_sources = set()

    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        passages.append({
            "text": doc,
            "filename": meta.get("filename", ""),
            "page_number": meta.get("page_number", 0),
            "category": meta.get("category", ""),
            "distance": dist,
        })
        source_key = (meta.get("filename", ""), meta.get("page_number", 0))
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            sources.append({
                "filename": meta.get("filename", ""),
                "page": meta.get("page_number", 0),
            })

    # Build context string for LLM consumption
    context_text = "\n\n---\n\n".join(
        f"[{p['filename']} p.{p['page_number']}]\n{p['text']}" for p in passages
    )

    return {
        "answer": context_text,
        "passages": passages,
        "sources": sources,
    }
