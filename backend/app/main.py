from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    description="AI-powered business document processing and automation platform.",
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    if (
        settings.app_env.lower() == "production"
        and request.url.scheme == "https"
    ):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response

if settings.app_env.lower() == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(
    documents_router,
    prefix=settings.api_v1_prefix,
)

app.include_router(
    auth_router,
    prefix=settings.api_v1_prefix,
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}