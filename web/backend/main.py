"""FastAPI backend for apartment recommendation app."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import apartments, nudge, detail, chat, knowledge, commute, feedback

app = FastAPI(title="Apartment Recommendation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apartments.router, prefix="/api")
app.include_router(nudge.router, prefix="/api")
app.include_router(detail.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(commute.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
