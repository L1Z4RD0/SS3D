import uuid

from pydantic import BaseModel


class FilamentBrandResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class FilamentMaterialResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class FilamentColorResponse(BaseModel):
    id: uuid.UUID
    name: str
    hex_color: str

    model_config = {"from_attributes": True}


class FilamentCatalogResponse(BaseModel):
    brands: list[FilamentBrandResponse]
    materials: list[FilamentMaterialResponse]
    colors: list[FilamentColorResponse]
