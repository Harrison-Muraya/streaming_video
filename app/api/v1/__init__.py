from fastapi import APIRouter
from app.api.v1 import auth, movies, admin, watch_history, recommendations

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(movies.router, prefix="/movies", tags=["Movies"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(watch_history.router, prefix="/watch", tags=["Watch History"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])


