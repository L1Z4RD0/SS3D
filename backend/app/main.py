from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import (
    admin,
    auth,
    business_profile,
    calculator,
    dashboard,
    filament_catalog,
    filaments,
    printers,
    quotes,
    sales,
    supplies,
)
from app.services.inventory import InsufficientStockError

app = FastAPI(title="Zola - Impresión 3D", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(InsufficientStockError)
def handle_insufficient_stock(request: Request, exc: InsufficientStockError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(printers.router)
app.include_router(filaments.router)
app.include_router(supplies.router)
app.include_router(calculator.router)
app.include_router(sales.router)
app.include_router(dashboard.router)
app.include_router(quotes.router)
app.include_router(business_profile.router)
app.include_router(filament_catalog.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
