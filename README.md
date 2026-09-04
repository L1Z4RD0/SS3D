# Zola — Gestión de negocio de impresión 3D

Aplicación web multiusuario que reemplaza el Excel de gestión: calculadora de precios, dashboard, registro de ventas, inventario (filamentos e insumos) e impresoras, con autenticación, roles (admin/usuario), multi-tenancy y auditoría.

## Estructura

```
Zola-App/
├── backend/    FastAPI + SQLAlchemy + Alembic + PostgreSQL
└── frontend/   Vue 3 + Vite + Pinia + Vue Router + Chart.js
```

## Requisitos previos

- **Python 3.11+** (probado con 3.14)
- **Node.js 18+** (probado con 22/24)
- **PostgreSQL 14+** instalado y corriendo localmente

Si no tienes PostgreSQL instalado en Windows, la forma más simple es:
- Instalador oficial: https://www.postgresql.org/download/windows/ (durante la instalación te pedirá definir la contraseña del usuario `postgres` — anótala).
- O con Docker (si lo tienes disponible): `docker run --name zola-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16`

## 1. Backend (FastAPI)

Abre una terminal en `backend/`.

### 1.1 Crear la base de datos

Con `psql` (ajusta usuario/contraseña según tu instalación):

```bash
psql -U postgres -h localhost -c "CREATE DATABASE zola_app;"
```

### 1.2 Entorno virtual y dependencias

El entorno virtual (`venv/`) ya fue creado y las dependencias ya están instaladas durante el desarrollo. Si necesitas recrearlo desde cero:

```bash
cd backend
python -m venv venv
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# Windows (Git Bash):
source venv/Scripts/activate

pip install -r requirements.txt
```

### 1.3 Variables de entorno

El archivo `backend/.env` ya existe con valores de desarrollo. Verifica que `DATABASE_URL` coincida con tu usuario/contraseña/puerto reales de PostgreSQL:

```
DATABASE_URL=postgresql+psycopg://postgres:TU_PASSWORD@localhost:5432/zola_app
SECRET_KEY=<ya generado, no lo compartas>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
CORS_ORIGINS=http://localhost:5173
```

### 1.4 Migraciones

```bash
cd backend
venv\Scripts\alembic upgrade head          # PowerShell / cmd
./venv/Scripts/alembic upgrade head        # Git Bash
```

Esto crea todas las tablas (`roles`, `users`, `refresh_tokens`, `audit_logs`, `printers`, `filaments`, `supplies`, `calculator_settings`, `sales`, `sale_supplies`).

### 1.5 Seed (usuario administrador inicial)

Antes de correr el seed, define el usuario/contraseña del admin inicial en `backend/.env`:

```
SEED_ADMIN_USERNAME=Lizard
SEED_ADMIN_PASSWORD=una-contraseña-que-no-uses-en-ningún-otro-sistema
```

No reutilices aquí una contraseña que ya uses para PostgreSQL, tu correo, etc. — este valor queda hasheado en la base de datos, pero si algún día compartes tu `.env` por error, no quieres que abra también otras cuentas tuyas.

Si dejas `SEED_ADMIN_PASSWORD` vacío, el script genera una contraseña aleatoria y la imprime **una sola vez** en la consola — cópiala de inmediato.

```bash
venv\Scripts\python -m app.seed          # PowerShell / cmd
./venv/Scripts/python -m app.seed        # Git Bash
```

Esto crea los roles `admin`/`user` y el usuario administrador con el usuario/contraseña que definiste (o el generado aleatoriamente). Si el usuario ya existe, el script no lo modifica — para rotar la contraseña de un admin existente, hazlo desde el panel (o directamente en la base de datos) en vez de re-correr el seed.

### 1.6 Levantar el servidor

```bash
venv\Scripts\uvicorn app.main:app --reload --port 8000          # PowerShell / cmd
./venv/Scripts/uvicorn app.main:app --reload --port 8000        # Git Bash
```

- API: http://localhost:8000
- Documentación interactiva (Swagger): http://localhost:8000/docs
- Salud: http://localhost:8000/api/health

## 2. Frontend (Vue 3 + Vite)

Abre **otra** terminal en `frontend/` (deja el backend corriendo en la primera).

```bash
cd frontend
npm install     # ya ejecutado, solo necesario si borras node_modules
npm run dev
```

- App: http://localhost:5173
- El archivo `frontend/.env` ya apunta a `VITE_API_URL=http://localhost:8000`.

Inicia sesión con el usuario/contraseña que hayas definido en `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` (paso 1.5).

## 3. Flujo de uso

1. Como **admin**, entra a **Administración** para crear usuarios adicionales (asignando rol `user` o `admin`).
2. Cada usuario (incluido el admin, para sí mismo) carga primero **Impresoras** e **Inventario** (filamentos e insumos) — son los datos maestros que alimentan los cálculos.
3. En **Calculadora**, configura tarifa eléctrica, valor hora de mano de obra e IVA (botón "Configuración"), y luego cotiza un trabajo. Puedes guardar cualquier escenario de margen directamente como venta.
4. **Ventas** permite crear/editar/eliminar ventas manualmente (con costos y stock recalculados automáticamente) y filtrar el historial.
5. **Dashboard** resume ingresos, ganancia, margen, desglose por impresora/método de pago y alertas de stock, con filtro de fechas.

## Notas de implementación (respecto a la propuesta de esquema)

- Se agregó `spool_weight_g` a `filaments` (no estaba explícito en la propuesta original) porque el costo de material depende del precio **por gramo** del carrete, no solo de su precio total.
- Los escenarios de margen (+60% a +200%) son configurables por usuario vía `calculator_settings.margin_scenarios`, no están hardcodeados.
- Impresoras/filamentos/insumos con ventas asociadas se **desactivan** en vez de eliminarse físicamente, para no romper el historial de costos ya calculado.
- Cada venta guarda un **snapshot** de sus costos (material, depreciación, energía, etc.) al momento de crearse — si luego cambias el precio de un filamento o el valor de una impresora, las ventas pasadas no se alteran.

## Troubleshooting

- **Error de conexión a la base de datos** al correr `alembic upgrade head` o levantar el backend: revisa que PostgreSQL esté corriendo (`pg_isready`) y que `DATABASE_URL` en `backend/.env` tenga el usuario/contraseña correctos.
- **401 constante en el frontend**: borra las cookies del sitio (`localhost:5173`) y vuelve a iniciar sesión — puede haber un refresh token viejo de una base de datos recreada.
- **CORS**: si cambias el puerto del frontend, actualiza `CORS_ORIGINS` en `backend/.env` y reinicia uvicorn.
