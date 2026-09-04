from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.business_profile import BusinessProfile
from app.models.user import User
from app.schemas.business_profile import BusinessProfileResponse, BusinessProfileUpdateRequest

router = APIRouter(prefix="/api/business-profile", tags=["business-profile"])


def _get_or_create(db: Session, user_id) -> BusinessProfile:
    profile = db.query(BusinessProfile).filter(BusinessProfile.user_id == user_id).first()
    if profile is None:
        profile = BusinessProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    return profile


@router.get("", response_model=BusinessProfileResponse)
def get_business_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = _get_or_create(db, current_user.id)
    db.commit()
    return profile


@router.put("", response_model=BusinessProfileResponse)
def update_business_profile(
    payload: BusinessProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = _get_or_create(db, current_user.id)
    profile.business_name = payload.business_name
    profile.logo_data_url = payload.logo_data_url
    db.commit()
    db.refresh(profile)
    return profile
