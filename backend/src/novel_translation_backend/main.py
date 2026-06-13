from fastapi import FastAPI

from novel_translation_backend.api.routes.workflow import router as workflow_router

app = FastAPI(title="AI Novel Translation API")
app.include_router(workflow_router)
