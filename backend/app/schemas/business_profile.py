from pydantic import BaseModel, Field

MAX_LOGO_DATA_URL_LENGTH = 700_000  # ~500KB image encoded as base64


class BusinessProfileResponse(BaseModel):
    business_name: str | None
    logo_data_url: str | None

    model_config = {"from_attributes": True}


class BusinessProfileUpdateRequest(BaseModel):
    business_name: str | None = Field(default=None, max_length=160)
    logo_data_url: str | None = Field(default=None, max_length=MAX_LOGO_DATA_URL_LENGTH)
