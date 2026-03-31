"""Chat feedback API."""

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from database import get_connection

router = APIRouter()
logger = logging.getLogger(__name__)

def _get_valid_tags():
    from common_codes import get_code_map
    return list(get_code_map("feedback_tag").keys())


class FeedbackRequest(BaseModel):
    user_message: str
    assistant_message: str
    tool_calls: list[dict] = []
    rating: int  # 1 = 좋아요, -1 = 싫어요
    tags: list[str] = []
    comment: str = ""
    session_id: str | None = None


class FeedbackResponse(BaseModel):
    id: int
    message: str


@router.post("/chat/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest):
    """Submit feedback for a chat response."""
    if req.rating not in (1, -1):
        return FeedbackResponse(id=0, message="rating must be 1 or -1")

    # Filter valid tags
    valid_tags = _get_valid_tags()
    tags = [t for t in req.tags if t in valid_tags]

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO chat_feedback
               (user_message, assistant_message, tool_calls, rating, tags, comment, session_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                req.user_message,
                req.assistant_message,
                json.dumps(req.tool_calls, ensure_ascii=False),
                req.rating,
                tags,
                req.comment,
                req.session_id,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        feedback_id = row[0] if row else 0

        logger.info(f"Feedback #{feedback_id}: rating={req.rating}, tags={tags}")
        return FeedbackResponse(id=feedback_id, message="피드백이 저장되었습니다.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Feedback save failed: {e}")
        return FeedbackResponse(id=0, message=f"저장 실패: {e}")
    finally:
        conn.close()


@router.get("/chat/feedback/stats")
async def feedback_stats():
    """Get feedback statistics."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chat_feedback WHERE rating = 1")
        likes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chat_feedback WHERE rating = -1")
        dislikes = cur.fetchone()[0]
        cur.execute("""
            SELECT unnest(tags) as tag, COUNT(*) as cnt
            FROM chat_feedback WHERE rating = -1
            GROUP BY tag ORDER BY cnt DESC
        """)
        tag_counts = {row[0]: row[1] for row in cur.fetchall()}
        return {
            "total": likes + dislikes,
            "likes": likes,
            "dislikes": dislikes,
            "satisfaction_rate": round(likes / (likes + dislikes) * 100, 1) if (likes + dislikes) > 0 else 0,
            "dislike_tags": tag_counts,
        }
    finally:
        conn.close()
