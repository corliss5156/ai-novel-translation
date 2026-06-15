from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from novel_translation_backend.api.config import settings
from novel_translation_backend.api.routes.chapters import router as chapters_router
from novel_translation_backend.api.routes.review import router as review_router
from novel_translation_backend.api.routes.workflow import router as workflow_router


FRONTEND_ORIGINS = ["http://localhost:5173"]

app = FastAPI(title="AI Novel Translation API")
app.state.settings = settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chapters_router)
app.include_router(workflow_router)
app.include_router(review_router)


@app.exception_handler(Exception)
async def handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
        },
    )
