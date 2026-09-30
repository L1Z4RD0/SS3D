import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.calculator import FilamentUsageInput, PlateInput, SupplyUsageInput

PAYMENT_METHODS = ("efectivo", "transferencia", "debito", "credito", "por_cobrar", "cortesia")
# Pagar "por cortesía" es regalar: el pedido se registra con precio $0 y sus costos
# (material, horas, insumos) quedan igual, como pérdida. El servidor fuerza el $0.
GIFT_PAYMENT_METHOD = "cortesia"


class SaleCreateRequest(BaseModel):
    # Fecha del pedido.
    sale_date: date
    # Fecha de entrega comprometida. Si no viene (ej. una versión vieja de la app en
    # caché), el servidor usa la fecha del pedido.
    promised_delivery_date: date | None = None
    client_name: str = Field(min_length=1, max_length=160)
    buyer_name: str | None = Field(default=None, max_length=160)
    # Solo para el observador (watcher): de qué usuario asignado es el inventario con que
    # se hace la venta. Para cualquier otro rol la venta es siempre del propio usuario.
    owner_id: uuid.UUID | None = None
    printer_id: uuid.UUID
    filaments: list[FilamentUsageInput] = Field(default_factory=list)
    print_hours: Decimal = Field(ge=0, default=0)
    postprocess_hours: Decimal = Field(ge=0, default=0)
    # Precio que se le cobra al cliente: el de un escenario sugerido o uno puesto a mano.
    price: Decimal = Field(ge=0)
    shipping_cost: Decimal = Field(ge=0, default=0)
    supplies: list[SupplyUsageInput] = Field(default_factory=list)
    payment_method: str = Field(pattern="^(" + "|".join(PAYMENT_METHODS) + ")$")
    notes: str | None = None
    # Planchas adicionales del mismo producto (la impresora/horas/filamentos de arriba son
    # la plancha principal).
    extra_plates: list[PlateInput] = Field(default_factory=list, max_length=20)


class SaleUpdateRequest(BaseModel):
    sale_date: date | None = None
    # Editable mientras el pedido no esté Entregado ni Cancelado.
    promised_delivery_date: date | None = None
    # Solo en Entregada: corrige la fecha real de entrega.
    delivered_date: date | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=160)
    buyer_name: str | None = Field(default=None, max_length=160)
    printer_id: uuid.UUID | None = None
    filaments: list[FilamentUsageInput] | None = None
    print_hours: Decimal | None = Field(default=None, ge=0)
    postprocess_hours: Decimal | None = Field(default=None, ge=0)
    # Si no viene, la venta conserva exactamente el precio con que se registró.
    price: Decimal | None = Field(default=None, ge=0)
    shipping_cost: Decimal | None = Field(default=None, ge=0)
    supplies: list[SupplyUsageInput] | None = None
    payment_method: str | None = Field(default=None, pattern="^(" + "|".join(PAYMENT_METHODS) + ")$")
    notes: str | None = None


class SaleStatusChangeRequest(BaseModel):
    status: str = Field(pattern="^(pendiente|en_produccion|lista|entregada|cancelado)$")
    # Pasar directo a Entregada desde Pendiente o En producción exige confirmarlo.
    skip_confirmed: bool = False
    # Día local del usuario (para la fecha real de entrega). Si no viene, hoy del servidor.
    today: date | None = None


class CancelOrderRequest(BaseModel):
    # ¿Dejar registradas las horas de impresión en la impresora? (En producción y Lista.)
    keep_hours: bool = True
    # En producción: "almacen" (la pieza sirve) o "inutilizable".
    # Lista: "almacen" o "descartar".
    piece_outcome: str | None = Field(default=None, pattern="^(almacen|inutilizable|descartar)$")
    # Si se descarta: regalada, danada, desechada u otro.
    discard_reason: str | None = Field(default=None, pattern="^(regalada|danada|desechada|otro)$")
    reason: str | None = Field(default=None, max_length=500)
    today: date | None = None


class WarehousePieceInfo(BaseModel):
    id: uuid.UUID
    status: str
    cost: Decimal
    price: Decimal


class DeliveryDateChangeRequest(BaseModel):
    promised_delivery_date: date


class CalendarOrder(BaseModel):
    """Versión liviana de un pedido para el Calendario."""

    id: uuid.UUID
    client_name: str
    buyer_name: str | None
    status: str
    sale_date: date
    promised_delivery_date: date
    delivered_date: date | None
    price: Decimal
    payment_method: str
    printer_name: str
    owner_id: uuid.UUID
    owner_username: str
    created_by_username: str | None
    can_edit: bool


class SaleStatusHistoryResponse(BaseModel):
    status: str
    changed_at: datetime
    changed_by_username: str | None
    note: str | None
    is_migration: bool


class SaleSupplyResponse(BaseModel):
    supply_id: uuid.UUID
    supply_name: str
    quantity_used: Decimal
    unit_cost_snapshot: Decimal
    # Unidades usadas sin stock, con costo provisional hasta que se repone el insumo.
    pending_qty: Decimal = Decimal(0)

    model_config = {"from_attributes": True}


class AddPlateRequest(PlateInput):
    # Reimpresión por fallo: suma costo sin cambiar el precio (la pérdida se ve en la ganancia).
    is_reprint: bool = False


class SalePlateFilamentResponse(BaseModel):
    filament_id: uuid.UUID
    filament_label: str
    grams_used: Decimal


class SalePlateResponse(BaseModel):
    id: uuid.UUID
    name: str
    printer_id: uuid.UUID
    printer_name: str
    print_hours: Decimal
    is_reprint: bool
    material_cost: Decimal
    depreciation_cost: Decimal
    energy_cost: Decimal
    total_cost: Decimal
    filaments: list[SalePlateFilamentResponse]


class SaleFilamentResponse(BaseModel):
    filament_id: uuid.UUID
    filament_label: str
    grams_used: Decimal
    material_cost_snapshot: Decimal

    model_config = {"from_attributes": True}


class ExhaustedFilamentInfo(BaseModel):
    filament_id: uuid.UUID
    filament_label: str

    model_config = {"from_attributes": True}


class SaleResponse(BaseModel):
    id: uuid.UUID
    sale_date: date
    client_name: str
    buyer_name: str | None
    # Dueño del inventario usado y quién registró la venta (pueden ser distintos si la
    # hizo un observador): se muestran siempre, por transparencia.
    owner_id: uuid.UUID
    owner_username: str
    created_by_user_id: uuid.UUID | None
    created_by_username: str | None
    printer_id: uuid.UUID
    printer_name: str
    filament_id: uuid.UUID | None
    filament_label: str | None
    grams_used: Decimal
    print_hours: Decimal
    postprocess_hours: Decimal
    # Lo que se le cobró al cliente.
    price: Decimal
    material_cost: Decimal
    depreciation_cost: Decimal
    energy_cost: Decimal
    postprocess_cost: Decimal
    supplies_cost: Decimal
    shipping_cost: Decimal
    total_cost: Decimal
    profit: Decimal
    margin_percent: Decimal
    payment_method: str
    notes: str | None
    # Ciclo de vida del pedido
    status: str
    promised_delivery_date: date
    delivered_date: date | None
    warehouse_item_id: uuid.UUID | None = None
    # Si quien consulta puede editarlo / cambiarle el estado (el dueño, o el observador
    # que lo registró). Los pedidos de sus asignados que no registró los ve solo lectura.
    can_edit: bool = True
    supplies_used: list[SaleSupplyResponse]
    # Algún insumo se usó sin stock: su costo (y la ganancia) es provisional hasta reponerlo.
    has_provisional_costs: bool = False
    # Planchas adicionales y reimpresiones (ya incluidas en los costos de arriba).
    plates: list[SalePlateResponse] = Field(default_factory=list)
    # Cuánto costaron las reimpresiones por fallo (parte del costo total).
    reprint_cost: Decimal = Decimal(0)
    filaments_used: list[SaleFilamentResponse]
    exhausted_filaments: list[ExhaustedFilamentInfo] = Field(default_factory=list)
    # Solo se incluye al pedir un pedido puntual o al cambiarle el estado.
    status_history: list[SaleStatusHistoryResponse] = Field(default_factory=list)
    # Cancelación
    cancel_reason: str | None = None
    loss_amount: Decimal = Decimal(0)
    # Pieza que este pedido dejó en el Almacén al cancelarse (si hay).
    warehouse_piece: WarehousePieceInfo | None = None

    model_config = {"from_attributes": True}


class SalePage(BaseModel):
    items: list[SaleResponse]
    total: int
