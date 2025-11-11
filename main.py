from fastapi import FastAPI
from app.routes.upload import router as upload_router
import uvicorn

app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local dev — later we will lock this down
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",     
        host="0.0.0.0",
        port=8000,
        reload=True
    )
