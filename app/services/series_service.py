"""
Service layer for Series, Season, Episode business logic
"""
import math
from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.series import Series, Season, Episode
from app.schemas.series import (
    SeriesCreate, SeriesUpdate,
    SeasonCreate, SeasonUpdate,
    EpisodeCreate, EpisodeUpdate
)


# ─────────────────────────────────────────────
# Series Service
# ─────────────────────────────────────────────

class SeriesService:

    @staticmethod
    def create_series(data: SeriesCreate, db: Session) -> Series:
        series = Series(**data.dict())
        db.add(series)
        db.commit()
        db.refresh(series)
        return series

    @staticmethod
    def get_series_by_id(series_id: int, db: Session) -> Series:
        series = db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Series {series_id} not found"
            )
        return series

    @staticmethod
    def get_all_series(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        featured: Optional[bool] = None,
        trending: Optional[bool] = None,
    ) -> dict:
        query = db.query(Series)

        if search:
            query = query.filter(Series.title.ilike(f"%{search}%"))
        if featured is not None:
            query = query.filter(Series.is_featured == featured)
        if trending is not None:
            query = query.filter(Series.is_trending == trending)

        total = query.count()
        total_pages = math.ceil(total / page_size)
        series_list = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "series": series_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    @staticmethod
    def update_series(series_id: int, data: SeriesUpdate, db: Session) -> Series:
        series = SeriesService.get_series_by_id(series_id, db)
        update_data = data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(series, key, value)
        db.commit()
        db.refresh(series)
        return series

    @staticmethod
    def delete_series(series_id: int, db: Session):
        series = SeriesService.get_series_by_id(series_id, db)
        db.delete(series)
        db.commit()
        return {"message": f"Series {series_id} deleted"}

    @staticmethod
    def increment_view(series_id: int, db: Session):
        series = SeriesService.get_series_by_id(series_id, db)
        series.view_count += 1
        db.commit()


# ─────────────────────────────────────────────
# Season Service
# ─────────────────────────────────────────────

class SeasonService:

    @staticmethod
    def create_season(series_id: int, data: SeasonCreate, db: Session) -> Season:
        # Ensure series exists
        SeriesService.get_series_by_id(series_id, db)

        # Check for duplicate season number
        existing = db.query(Season).filter(
            Season.series_id == series_id,
            Season.season_number == data.season_number
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Season {data.season_number} already exists for this series"
            )

        season = Season(series_id=series_id, **data.dict())
        db.add(season)
        db.commit()
        db.refresh(season)
        return season

    @staticmethod
    def get_season(season_id: int, db: Session) -> Season:
        season = db.query(Season).filter(Season.id == season_id).first()
        if not season:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Season {season_id} not found"
            )
        return season

    @staticmethod
    def update_season(season_id: int, data: SeasonUpdate, db: Session) -> Season:
        season = SeasonService.get_season(season_id, db)
        for key, value in data.dict(exclude_unset=True).items():
            setattr(season, key, value)
        db.commit()
        db.refresh(season)
        return season

    @staticmethod
    def delete_season(season_id: int, db: Session):
        season = SeasonService.get_season(season_id, db)
        db.delete(season)
        db.commit()
        return {"message": f"Season {season_id} deleted"}


# ─────────────────────────────────────────────
# Episode Service
# ─────────────────────────────────────────────

class EpisodeService:

    @staticmethod
    def create_episode(season_id: int, data: EpisodeCreate, db: Session) -> Episode:
        # Ensure season exists
        SeasonService.get_season(season_id, db)

        # Check for duplicate episode number
        existing = db.query(Episode).filter(
            Episode.season_id == season_id,
            Episode.episode_number == data.episode_number
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Episode {data.episode_number} already exists in this season"
            )

        episode = Episode(season_id=season_id, **data.dict())
        db.add(episode)
        db.commit()
        db.refresh(episode)
        return episode

    @staticmethod
    def get_episode(episode_id: int, db: Session) -> Episode:
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Episode {episode_id} not found"
            )
        return episode

    @staticmethod
    def update_episode(episode_id: int, data: EpisodeUpdate, db: Session) -> Episode:
        episode = EpisodeService.get_episode(episode_id, db)
        for key, value in data.dict(exclude_unset=True).items():
            setattr(episode, key, value)
        db.commit()
        db.refresh(episode)
        return episode

    @staticmethod
    def delete_episode(episode_id: int, db: Session):
        episode = EpisodeService.get_episode(episode_id, db)
        db.delete(episode)
        db.commit()
        return {"message": f"Episode {episode_id} deleted"}

    @staticmethod
    def increment_view(episode_id: int, db: Session):
        episode = EpisodeService.get_episode(episode_id, db)
        episode.view_count += 1
        db.commit()
