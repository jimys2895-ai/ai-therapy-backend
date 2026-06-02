import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Configure logging to stdout so Railway does not mark INFO logs as errors
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(levelname)s:%(name)s:%(message)s",
)

from .api.v1.auth.auth import router as auth_router
from .api.v1.users.users import router as users_router
from .api.v1.subscribe.plans import router as plans_router
from .api.v1.subscribe.subscription import router as subscription_router
from .api.v1.voice.patients import router as patients_router
from .api.v1.voice.history import router as history_router
from .api.v1.voice.voice import router as voice_router
from .api.v1.voice.settings import router as settings_router
from .api.v1.voice.dashboard import router as dashboard_router
from .api.v1.voice.insights import router as insights_router

from .config import settings
from .database import connect_to_mongo, close_mongo_connection

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    yield
    # Shutdown
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
    ## AI Therapy Backend API
    
    A.
    
    """,
    contact={
        "name": "AI Therapy API Support",
        "email": "support@aitherapy.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    servers=[
        {
            "url": "http://localhost:8000",
            "description": "Development server"  
        },
        {
            "url": "https://aitherapy-backend-production.up.railway.app",
            "description": "Production server"
        }
    ],
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000", "https://pocketshrink-frontend-production.up.railway.app"
                   ,"http://localhost:8000","https://ai-therapy-frontend-production.up.railway.app", "https://ai-therapy-frontend-production.up.railway.app/landing",
                   "https://frontend-production-9465.up.railway.app/landing","https://frontend-production-9465.up.railway.app"
                   ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routes
app.include_router(auth_router, prefix=settings.API_STR + "/auth", tags=["Authentication"])
app.include_router(users_router, prefix=settings.API_STR + "/users", tags=["User Management"])
app.include_router(plans_router, prefix=f"{settings.API_STR}/plans", tags=["Subscription Plans"])
app.include_router(subscription_router, prefix=f"{settings.API_STR}/subscription", tags=["Stripe Integration"])

# Voice/Therapy platform routes
app.include_router(patients_router, prefix=f"{settings.API_STR}/voice/patients", tags=["Patient Management"])
app.include_router(history_router, prefix=f"{settings.API_STR}/voice/history", tags=["Session History"])
app.include_router(voice_router, prefix=f"{settings.API_STR}/voice", tags=["Voice Processing"])
app.include_router(settings_router, prefix=f"{settings.API_STR}/voice/settings", tags=["User Settings"])
app.include_router(dashboard_router, prefix=f"{settings.API_STR}/voice/dashboard", tags=["Dashboard"])
app.include_router(insights_router, prefix=f"{settings.API_STR}/voice/insights", tags=["Session Insights"])

@app.get("/")
async def read_root():
    return {
        "message": "Welcome to the AI Therapy FastAPI Backend!",
        "version": settings.VERSION,
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}