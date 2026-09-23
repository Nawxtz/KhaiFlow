from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router

app = FastAPI(
    title="KhaiFlow Commerce API",
    description="Backend API for KhaiFlow chat commerce system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}
