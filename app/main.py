"""FastAPI Application Entry Point"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.config import settings
from app.api.routes import chat, bookings, webhooks, admin, availability, bandmember_email

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Initialize FastAPI app
app = FastAPI(
    title="AI Booking Agent API",
    description="AI-powered booking agent for coordinating live performances",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return JSONResponse(
        content={
            "status": "healthy",
            "environment": settings.environment,
            "version": "0.1.0"
        }
    )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Booking Agent API",
        "version": "0.1.0",
        "docs": "/docs" if settings.is_development else None
    }


# Include routers
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(bookings.router, prefix="/api/v1", tags=["bookings"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(availability.router, prefix="/api/v1", tags=["availability"])
app.include_router(bandmember_email.router, prefix="/api/v1/agent", tags=["agent"])


# Startup event
@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info(
        "application_starting",
        environment=settings.environment,
        base_url=settings.api_base_url
    )


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("application_shutting_down")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle uncaught exceptions"""
    logger.error(
        "uncaught_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred" if settings.is_production else str(exc)
        }
    )
