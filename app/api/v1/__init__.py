from fastapi import APIRouter
from app.api.v1 import auth
from app.api.v1 import movies
from app.api.v1 import admin
from app.api.v1 import watch_history
from app.api.v1 import recommendations
from app.api.v1 import series
from app.api.v1 import livestream
from app.api.v1 import series_watch

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(movies.router, prefix="/movies", tags=["Movies"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(watch_history.router, prefix="/watch", tags=["Watch History"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])
api_router.include_router(series.router, prefix="/series",tags=["Series"])
api_router.include_router(livestream.router, prefix="/live", tags=["Live Streaming"])
api_router.include_router(series_watch.router, prefix="/series-watch", tags=["Series Watch & Play Next"])
