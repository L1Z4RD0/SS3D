# Zola

App de gestión para negocio de impresión 3D (calculadora de precios, cotizaciones, ventas, inventario, impresoras, dashboard).

`backend/` FastAPI + PostgreSQL · `frontend/` Vue 3 + Vite

## Correr localmente

**Backend**

```bash
cd backend
./venv/Scripts/alembic upgrade head
./venv/Scripts/uvicorn app.main:app --reload --port 8000
```

**Frontend** (otra terminal)

```bash
cd frontend
npm run dev
```

`backend/.env` y `frontend/.env` ya están configurados localmente (no están en el repo). Login con el usuario definido en `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD`.
