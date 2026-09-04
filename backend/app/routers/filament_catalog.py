from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.filament_catalog import FilamentBrand, FilamentColor, FilamentMaterial
from app.models.user import User
from app.schemas.filament_catalog import FilamentCatalogResponse

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/filaments", response_model=FilamentCatalogResponse)
def get_filament_catalog(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return FilamentCatalogResponse(
        brands=db.query(FilamentBrand).order_by(FilamentBrand.name).all(),
        materials=db.query(FilamentMaterial).order_by(FilamentMaterial.name).all(),
        colors=db.query(FilamentColor).order_by(FilamentColor.name).all(),
    )
