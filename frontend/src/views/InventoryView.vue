<script setup>
import { ref, onMounted, reactive, computed, watch } from "vue";
import * as inventoryApi from "../api/inventory";
import { useObservedUsers } from "../composables/useObservedUsers";
import { formatCurrency, formatNumber, formatPercent, formatDate } from "../utils/format";
import { GRAMS_MAX, isValidNumber, extractApiError } from "../utils/validation";
import { confirmAction } from "../composables/useConfirm";
import { useFilamentCatalog, swatchFor, catalogHexFor, NEUTRAL_SWATCH } from "../composables/useFilamentCatalog";
import { useSupplyDebt } from "../composables/useSupplyDebt";
import { useAuthStore } from "../stores/auth";
import { todayISO } from "../utils/format";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";
import FilamentSpoolIcon from "../components/FilamentSpoolIcon.vue";

const auth = useAuthStore();

const CUSTOM = "__custom__";

const tab = ref("filaments");

const filaments = ref([]);
const supplies = ref([]);
const loadingFilaments = ref(true);
const loadingSupplies = ref(true);
const { catalog, ensureFilamentCatalog } = useFilamentCatalog();
// Los carretes en 0g se esconden por defecto: ya no sirven para un trabajo nuevo.
// El registro se conserva (tiene historial de ventas), solo deja de estorbar en la lista.
const showExhausted = ref(false);

const statusLabels = { disponible: "Disponible", alerta: "Alerta", critico: "Crítico", vacio: "Agotado" };
const statusBadge = { disponible: "badge-success", alerta: "badge-warning", critico: "badge-danger", vacio: "badge-danger" };


/* -------- Sort toggle (por gramos disponibles) -------- */
const sortDirection = ref(null); // null | 'desc' | 'asc'
function toggleExhausted() {
  showExhausted.value = !showExhausted.value;
  loadFilaments();
}

function toggleSort() {
  sortDirection.value = sortDirection.value === null ? "desc" : sortDirection.value === "desc" ? "asc" : null;
}
/* -------- Observador: inventario de cada usuario asignado por separado --------
   El backend le entrega al watcher los filamentos/insumos de todos sus usuarios
   juntos; acá se muestran de a un usuario a la vez para que no se mezclen. */
const { observedUsers, loadingObserved, loadObservedUsers } = useObservedUsers();
const selectedOwnerId = ref(null);

async function loadOwners() {
  await loadObservedUsers();
  if (!observedUsers.value.some((u) => u.id === selectedOwnerId.value)) {
    selectedOwnerId.value = observedUsers.value[0]?.id ?? null;
  }
}

function belongsToSelected(item) {
  return !auth.isWatcher || item.owner_id === selectedOwnerId.value;
}

const ownerFilaments = computed(() => filaments.value.filter(belongsToSelected));
const ownerSupplies = computed(() => supplies.value.filter(belongsToSelected));

function ownerCounts(userId) {
  return {
    filaments: filaments.value.filter((f) => f.owner_id === userId).length,
    supplies: supplies.value.filter((s) => s.owner_id === userId).length,
  };
}

const displayedFilaments = computed(() => {
  if (!sortDirection.value) return ownerFilaments.value;
  const sorted = [...ownerFilaments.value].sort((a, b) => Number(a.available_g) - Number(b.available_g));
  return sortDirection.value === "desc" ? sorted.reverse() : sorted;
});
const sortLabel = computed(() => {
  if (sortDirection.value === "desc") return "Stock: mayor a menor";
  if (sortDirection.value === "asc") return "Stock: menor a mayor";
  return "Ordenar por stock";
});

async function loadFilaments() {
  loadingFilaments.value = true;
  try {
    filaments.value = await inventoryApi.listFilaments(false, showExhausted.value);
  } finally {
    loadingFilaments.value = false;
  }
}

async function loadSupplies() {
  loadingSupplies.value = true;
  try {
    supplies.value = await inventoryApi.listSupplies();
  } finally {
    loadingSupplies.value = false;
  }
}

onMounted(() => {
  if (auth.isWatcher) loadOwners();
  loadFilaments();
  loadSupplies();
  ensureFilamentCatalog();
});

/* -------- Filaments -------- */
const showFilamentModal = ref(false);
const editingFilamentId = ref(null);
const filamentSaving = ref(false);
const filamentError = ref("");
const emptyFilamentForm = () => ({
  brand: "",
  type: "PLA",
  color: "",
  color_hex: NEUTRAL_SWATCH,
  sku: "",
  entry_date: todayISO(),
  spool_weight_g: 1000,
  initial_stock_g: null,
  min_alert_g: 100,
  spool_price: null,
});
const filamentForm = reactive(emptyFilamentForm());
const customBrandText = ref("");
const customMaterialText = ref("");
const customColorText = ref("");

/* Color: los del catálogo son atajos (nombre + tono); el selector RGB ajusta el tono exacto. */
const HEX_RE = /^#[0-9a-fA-F]{6}$/;
function pickCatalogColor(c) {
  filamentForm.color = c.name;
  filamentForm.color_hex = c.hex_color;
}
function pickCustomColor() {
  filamentForm.color = CUSTOM;
}
// Campo de texto para pegar un código (#RRGGBB); solo se aplica cuando está completo.
const hexText = ref("");
watch(
  () => filamentForm.color_hex,
  (hex) => {
    hexText.value = (hex || "").toUpperCase();
  },
  { immediate: true }
);
function onHexText(value) {
  let v = value.trim();
  if (v && !v.startsWith("#")) v = `#${v}`;
  hexText.value = v.toUpperCase();
  if (HEX_RE.test(v)) filamentForm.color_hex = v.toLowerCase();
}
const multiRoll = ref(false);
const multiRollCount = ref(2);

function openCreateFilament() {
  editingFilamentId.value = null;
  Object.assign(filamentForm, emptyFilamentForm());
  filamentForm.type = catalog.value.materials.some((m) => m.name === "PLA") ? "PLA" : "";
  customBrandText.value = "";
  customMaterialText.value = "";
  customColorText.value = "";
  multiRoll.value = false;
  multiRollCount.value = 2;
  filamentError.value = "";
  showFilamentModal.value = true;
}

function openEditFilament(f) {
  editingFilamentId.value = f.id;
  const brandMatch = catalog.value.brands.some((b) => b.name === f.brand);
  const materialMatch = catalog.value.materials.some((m) => m.name === f.type);
  const colorMatch = catalog.value.colors.some((c) => c.name === f.color);
  Object.assign(filamentForm, {
    brand: brandMatch ? f.brand : CUSTOM,
    type: materialMatch ? f.type : CUSTOM,
    color: colorMatch ? f.color : CUSTOM,
    color_hex: f.color_hex || catalogHexFor(f.color) || NEUTRAL_SWATCH,
    sku: f.sku || "",
    entry_date: f.entry_date,
    spool_weight_g: Number(f.spool_weight_g),
    initial_stock_g: Number(f.initial_stock_g),
    min_alert_g: Number(f.min_alert_g),
    spool_price: Number(f.spool_price),
  });
  customBrandText.value = brandMatch ? "" : f.brand;
  customMaterialText.value = materialMatch ? "" : f.type;
  customColorText.value = colorMatch ? "" : f.color;
  filamentError.value = "";
  showFilamentModal.value = true;
}

function validateFilamentForm() {
  if (!filamentForm.color || (filamentForm.color === CUSTOM && !customColorText.value.trim())) {
    return "Elige un color del catálogo o escribe el nombre de tu color.";
  }
  if (!HEX_RE.test(filamentForm.color_hex || "")) {
    return "El tono exacto debe tener el formato #RRGGBB (ej. #1ABC9C).";
  }
  if (!isValidNumber(filamentForm.spool_weight_g, { min: 0, max: GRAMS_MAX, allowZero: false })) {
    return `El peso del carrete debe ser mayor a 0 y no superar ${GRAMS_MAX}g.`;
  }
  if (!isValidNumber(filamentForm.initial_stock_g, { min: 0, max: GRAMS_MAX, allowZero: false })) {
    return `El stock inicial debe ser mayor a 0 y no superar ${GRAMS_MAX}g.`;
  }
  if (!isValidNumber(filamentForm.min_alert_g, { min: 0, max: GRAMS_MAX })) {
    return `La alerta mínima no puede ser negativa ni superar ${GRAMS_MAX}g.`;
  }
  if (!isValidNumber(filamentForm.spool_price, { min: 0, allowZero: false })) {
    return "El precio del carrete debe ser mayor a 0.";
  }
  return "";
}

async function submitFilament() {
  const validationError = validateFilamentForm();
  if (validationError) {
    filamentError.value = validationError;
    return;
  }
  const isMultiRoll = !editingFilamentId.value && multiRoll.value;
  if (isMultiRoll && !isValidNumber(multiRollCount.value, { min: 2, max: 50 })) {
    filamentError.value = "La cantidad de rollos debe ser un número entre 2 y 50.";
    return;
  }

  filamentSaving.value = true;
  filamentError.value = "";
  const baseSku = filamentForm.sku?.trim() || "";
  const payload = {
    ...filamentForm,
    brand: filamentForm.brand === CUSTOM ? customBrandText.value : filamentForm.brand,
    type: filamentForm.type === CUSTOM ? customMaterialText.value : filamentForm.type,
    color: filamentForm.color === CUSTOM ? customColorText.value : filamentForm.color,
    sku: baseSku || null,
  };
  let createdCount = 0;
  try {
    if (editingFilamentId.value) {
      await inventoryApi.updateFilament(editingFilamentId.value, payload);
    } else if (isMultiRoll) {
      const count = Math.round(multiRollCount.value);
      for (let i = 1; i <= count; i++) {
        await inventoryApi.createFilament({
          ...payload,
          // Cada rollo necesita su propio SKU (son únicos por usuario) -- si el
          // usuario puso uno base, le agregamos un sufijo por rollo para seguir
          // pudiendo distinguirlos; si lo dejó vacío, todos quedan sin SKU (los
          // SKU nulos no chocan entre sí).
          sku: baseSku ? `${baseSku}-${i}` : null,
        });
        createdCount++;
      }
    } else {
      await inventoryApi.createFilament(payload);
      createdCount = 1;
    }
    showFilamentModal.value = false;
  } catch (err) {
    if (isMultiRoll) {
      const count = Math.round(multiRollCount.value);
      filamentError.value = `Se crearon ${createdCount} de ${count} rollos antes de un error: ${extractApiError(err, "error desconocido")}`;
    } else {
      filamentError.value = extractApiError(err, "No se pudo guardar el filamento.");
    }
  } finally {
    if (createdCount > 0 || editingFilamentId.value) {
      await loadFilaments();
    }
    filamentSaving.value = false;
  }
}

async function deleteFilament(f) {
  const ok = await confirmAction({
    title: "Eliminar filamento",
    message: `¿Eliminar "${f.brand} ${f.color}"? Si tiene ventas asociadas, se desactivará.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  await inventoryApi.deleteFilament(f.id);
  await loadFilaments();
}

/* -------- Reponer insumo -------- */
const { refreshSupplyDebt } = useSupplyDebt();
const restockTarget = ref(null);
const restockForm = reactive({ quantity: null, total_cost: null });
const restockBusy = ref(false);
const restockError = ref("");
const restockResult = ref("");

function openRestock(s) {
  restockTarget.value = s;
  Object.assign(restockForm, {
    quantity: Number(s.owed_qty) > 0 ? Number(s.owed_qty) : null,
    total_cost: null,
  });
  restockError.value = "";
}

// Vista previa: cuánto de lo fiado cubre esta compra y a qué precio queda cada unidad.
const restockPreview = computed(() => {
  const s = restockTarget.value;
  const qty = Number(restockForm.quantity);
  const total = Number(restockForm.total_cost);
  if (!s || !(qty > 0) || restockForm.total_cost === null || restockForm.total_cost === "" || total < 0) return null;
  const unit = total / qty;
  const pending = Number(s.pending_cost_qty);
  const settled = Math.min(qty, pending);
  return {
    unit,
    settled,
    stockAfter: Number(s.quantity_available) + qty,
    // Aproximado: las unidades fiadas se costearon al precio que tenía el insumo.
    adjustment: s.unit_cost !== null ? settled * (unit - Number(s.unit_cost)) : null,
  };
});

async function confirmRestock() {
  if (!isValidNumber(restockForm.quantity, { min: 0, allowZero: false })) {
    restockError.value = "Indica cuántas unidades compraste (mayor a 0).";
    return;
  }
  if (!isValidNumber(restockForm.total_cost, { min: 0 })) {
    restockError.value = "Indica cuánto pagaste en total por la compra.";
    return;
  }
  restockBusy.value = true;
  restockError.value = "";
  try {
    const res = await inventoryApi.restockSupply(restockTarget.value.id, {
      quantity: Number(restockForm.quantity),
      total_cost: Number(restockForm.total_cost),
    });
    const name = restockTarget.value.name;
    restockTarget.value = null;
    const adj = Number(res.cost_adjustment);
    restockResult.value =
      res.repriced_sales > 0
        ? `${name}: se registró la compra y se corrigió el costo de ${res.repriced_sales} venta(s) ` +
          `(${adj >= 0 ? "+" : "−"}${formatCurrency(Math.abs(adj))} en costos).`
        : `${name}: se registró la compra.`;
    await loadSupplies();
    refreshSupplyDebt();
  } catch (err) {
    restockError.value = extractApiError(err, "No se pudo registrar la compra.");
  } finally {
    restockBusy.value = false;
  }
}

/* -------- Supplies -------- */
const showSupplyModal = ref(false);
const editingSupplyId = ref(null);
const supplySaving = ref(false);
const supplyError = ref("");
const emptySupplyForm = () => ({
  name: "",
  category: "",
  quantity_available: null,
  min_alert_qty: null,
  purchase_quantity: null,
  purchase_total_cost: null,
});
const supplyForm = reactive(emptySupplyForm());

const computedUnitCost = computed(() => {
  const qty = Number(supplyForm.purchase_quantity);
  const total = Number(supplyForm.purchase_total_cost);
  if (!qty || total === null || total === undefined || Number.isNaN(total)) return null;
  return total / qty;
});

function openCreateSupply() {
  editingSupplyId.value = null;
  Object.assign(supplyForm, emptySupplyForm());
  supplyError.value = "";
  showSupplyModal.value = true;
}

const editingSupplyQty = ref(null);

function openEditSupply(s) {
  editingSupplyId.value = s.id;
  editingSupplyQty.value = Number(s.quantity_available);
  Object.assign(supplyForm, {
    name: s.name,
    category: s.category,
    quantity_available: Number(s.quantity_available),
    min_alert_qty: s.min_alert_qty !== null ? Number(s.min_alert_qty) : null,
    purchase_quantity: s.purchase_quantity !== null ? Number(s.purchase_quantity) : null,
    purchase_total_cost: s.purchase_total_cost !== null ? Number(s.purchase_total_cost) : null,
  });
  supplyError.value = "";
  showSupplyModal.value = true;
}

const supplyQtyChanged = () =>
  !editingSupplyId.value || Number(supplyForm.quantity_available) !== editingSupplyQty.value;

function validateSupplyForm() {
  if (supplyQtyChanged() && !isValidNumber(supplyForm.quantity_available, { min: 0 })) {
    return "La cantidad disponible no puede ser negativa.";
  }
  if (supplyForm.min_alert_qty !== null && !isValidNumber(supplyForm.min_alert_qty, { min: 0 })) {
    return "La alerta mínima no puede ser negativa.";
  }
  const hasQty = supplyForm.purchase_quantity !== null && supplyForm.purchase_quantity !== "";
  const hasCost = supplyForm.purchase_total_cost !== null && supplyForm.purchase_total_cost !== "";
  if (hasQty !== hasCost) {
    return "Indica tanto la cantidad comprada como el costo total, o deja ambos vacíos.";
  }
  if (hasQty && !isValidNumber(supplyForm.purchase_quantity, { min: 0, allowZero: false })) {
    return "La cantidad comprada debe ser mayor a 0.";
  }
  if (hasCost && !isValidNumber(supplyForm.purchase_total_cost, { min: 0 })) {
    return "El costo total de la compra no puede ser negativo.";
  }
  return "";
}

async function submitSupply() {
  const validationError = validateSupplyForm();
  if (validationError) {
    supplyError.value = validationError;
    return;
  }
  supplySaving.value = true;
  supplyError.value = "";
  try {
    if (editingSupplyId.value) {
      // Un insumo en negativo se puede editar (nombre, alerta...) sin tocar su cantidad:
      // lo que se debe se salda con Reponer, para corregir el costo de las ventas.
      const { quantity_available, ...rest } = supplyForm;
      await inventoryApi.updateSupply(editingSupplyId.value, supplyQtyChanged() ? supplyForm : rest);
    } else {
      await inventoryApi.createSupply(supplyForm);
    }
    showSupplyModal.value = false;
    await loadSupplies();
    refreshSupplyDebt();
  } catch (err) {
    supplyError.value = extractApiError(err, "No se pudo guardar el insumo.");
  } finally {
    supplySaving.value = false;
  }
}

async function deleteSupply(s) {
  const ok = await confirmAction({
    title: "Eliminar insumo",
    message: `¿Eliminar "${s.name}"? Si tiene ventas asociadas, se desactivará.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!ok) return;
  await inventoryApi.deleteSupply(s.id);
  await loadSupplies();
}
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Stock de filamentos e insumos, con alertas automáticas de nivel mínimo</p>
    </div>

    <div v-if="auth.isWatcher" class="card owner-picker">
      <div v-if="loadingObserved && !observedUsers.length" class="text-muted text-sm">Cargando usuarios...</div>
      <div v-else-if="!observedUsers.length" class="text-muted text-sm">
        Todavía no tienes usuarios asignados. Pídele al administrador que te asigne a quién observar.
      </div>
      <template v-else>
        <span class="owner-picker-label">Inventario de</span>
        <div class="owner-picker-list" role="group" aria-label="Usuario cuyo inventario ver">
          <button
            v-for="u in observedUsers"
            :key="u.id"
            type="button"
            class="owner-chip"
            :class="{ selected: selectedOwnerId === u.id }"
            :aria-pressed="selectedOwnerId === u.id"
            @click="selectedOwnerId = u.id"
          >
            <strong>{{ u.username }}</strong>
            <span class="owner-chip-meta">
              {{ ownerCounts(u.id).filaments }} filamentos · {{ ownerCounts(u.id).supplies }} insumos
            </span>
          </button>
        </div>
      </template>
    </div>

    <div class="tabs">
      <button class="tab-btn" :class="{ active: tab === 'filaments' }" @click="tab = 'filaments'">Filamentos</button>
      <button class="tab-btn" :class="{ active: tab === 'supplies' }" @click="tab = 'supplies'">Insumos</button>
    </div>

    <div v-if="tab === 'filaments'" class="card">
      <div class="card-header">
        <h3>Filamentos</h3>
        <div class="flex gap-2">
          <button class="btn btn-secondary btn-sm" @click="toggleExhausted">
            {{ showExhausted ? "Ocultar agotados" : "Ver agotados" }}
          </button>
          <button class="btn btn-secondary btn-sm" @click="toggleSort">
            <Icon name="filter" :size="14" />
            {{ sortLabel }}
          </button>
          <button v-if="!auth.isWatcher" class="btn btn-primary btn-sm" @click="openCreateFilament">
            <Icon name="plus" :size="15" /> Nuevo filamento
          </button>
        </div>
      </div>

      <div v-if="loadingFilaments" class="empty-state">Cargando...</div>
      <div v-else-if="!ownerFilaments.length" class="empty-state">
        <h3>Sin filamentos registrados</h3>
        <p v-if="auth.isWatcher">Este usuario no tiene filamentos{{ showExhausted ? "" : " con stock" }}.</p>
        <p v-else>Agrega tu primer carrete para empezar a llevar el stock.</p>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Filamento</th>
              <th>Ingreso</th>
              <th class="text-right">Disponible</th>
              <th class="text-right">% stock</th>
              <th>Estado</th>
              <th class="text-right">Precio carrete</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in displayedFilaments" :key="f.id">
              <td>
                <div class="flex items-center gap-2">
                  <FilamentSpoolIcon :color="swatchFor(f)" :size="40" />
                  <div>
                    <strong>{{ f.brand }} · {{ f.color }}</strong>
                    <span v-if="f.sku" class="badge badge-neutral" style="margin-left: 6px">{{ f.sku }}</span>
                    <div class="text-muted text-sm">{{ f.type }}</div>
                  </div>
                </div>
              </td>
              <td>{{ formatDate(f.entry_date) }}</td>
              <td class="text-right mono">{{ formatNumber(f.available_g, 0) }} g</td>
              <td class="text-right mono">{{ formatPercent(f.stock_percent) }}</td>
              <td><span class="badge" :class="statusBadge[f.stock_status]">{{ statusLabels[f.stock_status] }}</span></td>
              <td class="text-right mono">{{ formatCurrency(f.spool_price) }}</td>
              <td class="text-right">
                <div v-if="!auth.isWatcher" class="flex gap-2" style="justify-content: flex-end">
                  <button class="btn btn-icon btn-ghost" @click="openEditFilament(f)"><Icon name="edit" :size="16" /></button>
                  <button class="btn btn-icon btn-ghost" @click="deleteFilament(f)"><Icon name="trash" :size="16" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else class="card">
      <div class="card-header">
        <h3>Insumos y accesorios</h3>
        <button v-if="!auth.isWatcher" class="btn btn-primary btn-sm" @click="openCreateSupply">
          <Icon name="plus" :size="15" /> Nuevo insumo
        </button>
      </div>

      <div v-if="restockResult" class="alert alert-success" style="margin-bottom: 12px">
        <span style="flex: 1">{{ restockResult }}</span>
        <button type="button" class="btn btn-icon btn-ghost btn-sm" aria-label="Cerrar" @click="restockResult = ''">✕</button>
      </div>
      <div v-if="loadingSupplies" class="empty-state">Cargando...</div>
      <div v-else-if="!ownerSupplies.length" class="empty-state">
        <h3>Sin insumos registrados</h3>
        <p v-if="auth.isWatcher">Este usuario no tiene insumos registrados.</p>
        <p v-else>Agrega argollas, imanes, pegamento u otros consumibles.</p>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Insumo</th>
              <th>Categoría</th>
              <th class="text-right">Cantidad disponible</th>
              <th class="text-right">Costo unitario</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in ownerSupplies" :key="s.id">
              <td><strong>{{ s.name }}</strong></td>
              <td>{{ s.category }}</td>
              <td class="text-right mono" :class="{ 'qty-negative': Number(s.quantity_available) < 0 }">
                {{ formatNumber(s.quantity_available, 0) }}
              </td>
              <td class="text-right mono">
                <div>{{ s.unit_cost !== null ? formatCurrency(s.unit_cost) : "-" }}</div>
                <div v-if="s.purchase_quantity" class="text-muted text-sm">
                  {{ formatNumber(s.purchase_quantity, 0) }} uds. por {{ formatCurrency(s.purchase_total_cost) }}
                </div>
              </td>
              <td>
                <span v-if="Number(s.owed_qty) > 0" class="badge badge-danger">Debes {{ formatNumber(s.owed_qty, 0) }}</span>
                <span v-else-if="s.low_stock" class="badge badge-warning">Stock bajo</span>
                <span v-else class="badge badge-success">OK</span>
                <div v-if="Number(s.pending_cost_qty) > 0" class="text-sm pending-cost-hint">
                  {{ formatNumber(s.pending_cost_qty, 0) }} ud(s). con costo provisional
                </div>
              </td>
              <td class="text-right">
                <div v-if="!auth.isWatcher" class="flex gap-2" style="justify-content: flex-end">
                  <button
                    class="btn btn-sm"
                    :class="Number(s.owed_qty) > 0 ? 'btn-danger' : 'btn-secondary'"
                    title="Registrar una compra de este insumo"
                    @click="openRestock(s)"
                  >
                    <Icon name="plus" :size="14" /> Reponer
                  </button>
                  <button class="btn btn-icon btn-ghost" @click="openEditSupply(s)"><Icon name="edit" :size="16" /></button>
                  <button class="btn btn-icon btn-ghost" @click="deleteSupply(s)"><Icon name="trash" :size="16" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal persistent v-if="restockTarget" title="Reponer insumo" :subtitle="restockTarget.name" width="500px" @close="restockTarget = null">
      <form @submit.prevent="confirmRestock">
        <div v-if="Number(restockTarget.owed_qty) > 0" class="alert alert-danger" style="margin-bottom: 14px">
          Debes {{ formatNumber(restockTarget.owed_qty, 0) }} unidad(es). La compra cubre primero lo que se usó sin stock y
          corrige el costo de esas ventas al precio real.
        </div>
        <div class="form-grid">
          <div class="field">
            <label>Cantidad comprada</label>
            <input v-model.number="restockForm.quantity" type="number" min="1" step="1" required />
          </div>
          <div class="field">
            <label>Total pagado (CLP)</label>
            <input v-model.number="restockForm.total_cost" type="number" min="0" step="1" required placeholder="Ej: 5000" />
          </div>
        </div>
        <div v-if="restockPreview" class="restock-preview mt-2">
          <div><span>Costo por unidad</span><strong class="mono">{{ formatCurrency(restockPreview.unit) }}</strong></div>
          <div v-if="restockTarget.unit_cost !== null">
            <span>Costo anterior</span><span class="mono">{{ formatCurrency(restockTarget.unit_cost) }}</span>
          </div>
          <div v-if="restockPreview.settled > 0">
            <span>Unidades fiadas que se saldan</span><strong class="mono">{{ formatNumber(restockPreview.settled, 0) }}</strong>
          </div>
          <div v-if="restockPreview.settled > 0 && restockPreview.adjustment !== null">
            <span>Ajuste aprox. en el costo de esas ventas</span>
            <strong class="mono" :style="{ color: restockPreview.adjustment > 0 ? 'var(--danger)' : 'var(--success)' }">
              {{ restockPreview.adjustment >= 0 ? "+" : "−" }}{{ formatCurrency(Math.abs(restockPreview.adjustment)) }}
            </strong>
          </div>
          <div>
            <span>Stock después de reponer</span>
            <strong class="mono" :class="{ 'qty-negative': restockPreview.stockAfter < 0 }">
              {{ formatNumber(restockPreview.stockAfter, 0) }}
            </strong>
          </div>
        </div>
        <div v-if="restockError" class="alert alert-danger mt-4">{{ restockError }}</div>
        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="restockTarget = null">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="restockBusy">
            {{ restockBusy ? "Guardando..." : "Registrar compra" }}
          </button>
        </div>
      </form>
    </Modal>

    <Modal persistent v-if="showFilamentModal" :title="editingFilamentId ? 'Editar filamento' : 'Nuevo filamento'" @close="showFilamentModal = false">
      <form @submit.prevent="submitFilament">
        <div class="form-grid">
          <div class="field">
            <label>Marca</label>
            <select v-model="filamentForm.brand" required>
              <option value="" disabled>Selecciona una marca</option>
              <option v-for="b in catalog.brands" :key="b.id" :value="b.name">{{ b.name }}</option>
              <option :value="CUSTOM">Otra marca...</option>
            </select>
            <input v-if="filamentForm.brand === CUSTOM" v-model="customBrandText" placeholder="Nombre de la marca" class="mt-2" required />
          </div>
          <div class="field">
            <label>Material</label>
            <select v-model="filamentForm.type" required>
              <option value="" disabled>Selecciona un material</option>
              <option v-for="m in catalog.materials" :key="m.id" :value="m.name">{{ m.name }}</option>
              <option :value="CUSTOM">Otro material...</option>
            </select>
            <input v-if="filamentForm.type === CUSTOM" v-model="customMaterialText" placeholder="Nombre del material" class="mt-2" required />
          </div>
          <div class="field" style="grid-column: span 2">
            <label>Color</label>
            <div class="color-editor">
              <div class="color-preview" :title="`Vista previa: ${filamentForm.color_hex}`">
                <FilamentSpoolIcon :color="filamentForm.color_hex" :size="72" />
              </div>
              <div class="color-editor-controls">
                <div class="color-swatch-grid">
                  <button
                    v-for="c in catalog.colors"
                    :key="c.id"
                    type="button"
                    class="color-swatch"
                    :class="{ selected: filamentForm.color === c.name }"
                    :style="{ background: c.hex_color }"
                    :title="c.name"
                    @click="pickCatalogColor(c)"
                  ></button>
                  <button
                    type="button"
                    class="color-swatch color-swatch-custom"
                    :class="{ selected: filamentForm.color === CUSTOM }"
                    title="Otro color"
                    @click="pickCustomColor"
                  >+</button>
                </div>
                <div class="color-exact">
                  <label class="color-exact-picker" title="Elegir el tono exacto">
                    <input v-model="filamentForm.color_hex" type="color" aria-label="Tono exacto (RGB)" />
                    <span>Tono exacto (RGB)</span>
                  </label>
                  <input
                    class="color-exact-hex mono"
                    :value="hexText"
                    maxlength="7"
                    placeholder="#RRGGBB"
                    aria-label="Código de color hexadecimal"
                    @input="onHexText($event.target.value)"
                  />
                </div>
              </div>
            </div>
            <span v-if="filamentForm.color && filamentForm.color !== CUSTOM" class="field-hint">
              Seleccionado: {{ filamentForm.color }} · puedes ajustar el tono con el selector RGB.
            </span>
            <input v-if="filamentForm.color === CUSTOM" v-model="customColorText" placeholder="Nombre del color (ej. Verde agua)" class="mt-2" required />
          </div>
          <div class="field" style="grid-column: span 2">
            <label>SKU / Identificador (opcional)</label>
            <input v-model="filamentForm.sku" placeholder="Ej: ROJO-01, para diferenciar carretes iguales" maxlength="60" />
          </div>
          <div v-if="!editingFilamentId" class="field" style="grid-column: span 2">
            <label class="flex items-center gap-2" style="cursor: pointer; font-weight: 600">
              <input v-model="multiRoll" type="checkbox" style="width: auto" />
              Agregar varios rollos iguales de una vez
            </label>
            <span class="field-hint">Crea varios filamentos idénticos (mismo color, peso, stock y precio) en una sola operación.</span>
            <input
              v-if="multiRoll"
              v-model.number="multiRollCount"
              type="number"
              min="2"
              max="50"
              step="1"
              placeholder="Cantidad de rollos"
              class="mt-2"
              style="max-width: 160px"
            />
          </div>
          <div class="field">
            <label>Fecha de ingreso</label>
            <input v-model="filamentForm.entry_date" type="date" required />
          </div>
          <div class="field">
            <label>Peso del carrete (g)</label>
            <input v-model.number="filamentForm.spool_weight_g" type="number" min="0.01" :max="GRAMS_MAX" step="0.01" required />
          </div>
          <div class="field">
            <label>Precio del carrete (CLP)</label>
            <input v-model.number="filamentForm.spool_price" type="number" min="0" step="1" required />
          </div>
          <div class="field">
            <label>Stock inicial (g)</label>
            <input v-model.number="filamentForm.initial_stock_g" type="number" min="0.01" :max="GRAMS_MAX" step="0.01" required />
          </div>
          <div class="field">
            <label>Alerta mínima (g)</label>
            <input v-model.number="filamentForm.min_alert_g" type="number" min="0" :max="GRAMS_MAX" step="0.01" required />
          </div>
        </div>

        <div v-if="filamentError" class="alert alert-danger mt-4">{{ filamentError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showFilamentModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="filamentSaving">
            {{ filamentSaving ? "Guardando..." : !editingFilamentId && multiRoll ? `Crear ${multiRollCount || 0} rollos` : "Guardar" }}
          </button>
        </div>
      </form>
    </Modal>

    <Modal persistent v-if="showSupplyModal" :title="editingSupplyId ? 'Editar insumo' : 'Nuevo insumo'" @close="showSupplyModal = false">
      <form @submit.prevent="submitSupply">
        <div class="form-grid">
          <div class="field">
            <label>Nombre</label>
            <input v-model="supplyForm.name" required />
          </div>
          <div class="field">
            <label>Categoría</label>
            <input v-model="supplyForm.category" placeholder="Argollas, imanes, pegamento..." required />
          </div>
          <div class="field">
            <label>Cantidad disponible</label>
            <input v-model.number="supplyForm.quantity_available" type="number" min="0" step="1" required />
          </div>
          <div class="field">
            <label>Alerta mínima</label>
            <input v-model.number="supplyForm.min_alert_qty" type="number" min="0" step="1" />
          </div>
        </div>

        <h3 class="mt-4" style="font-size: 0.95rem; margin-bottom: 10px">Última compra (para calcular el costo unitario)</h3>
        <div class="form-grid">
          <div class="field">
            <label>Cantidad comprada</label>
            <input v-model.number="supplyForm.purchase_quantity" type="number" min="1" step="1" placeholder="Ej: 100" />
          </div>
          <div class="field">
            <label>Costo total de la compra (CLP)</label>
            <input v-model.number="supplyForm.purchase_total_cost" type="number" min="0" step="1" placeholder="Ej: 10000" />
          </div>
        </div>
        <p class="field-hint mt-2">
          Costo unitario calculado:
          <strong>{{ computedUnitCost !== null ? formatCurrency(computedUnitCost) : "— completa ambos campos" }}</strong>
        </p>

        <div v-if="supplyError" class="alert alert-danger mt-4">{{ supplyError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showSupplyModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="supplySaving">
            {{ supplySaving ? "Guardando..." : "Guardar" }}
          </button>
        </div>
      </form>
    </Modal>
  </div>
</template>

<style scoped>
.owner-picker {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.owner-picker-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
}

.owner-picker-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.owner-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.owner-chip.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.owner-chip:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--primary-soft);
}

.owner-chip-meta {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.color-swatch-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.color-swatch {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1px solid var(--border);
  cursor: pointer;
  padding: 0;
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}

.color-swatch:hover {
  transform: scale(1.08);
}

.color-swatch.selected {
  box-shadow: 0 0 0 2px var(--surface), 0 0 0 4px var(--primary);
}

.color-swatch-custom {
  background: var(--surface-alt);
  color: var(--text-muted);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.color-editor {
  display: flex;
  align-items: center;
  gap: 16px;
}

.color-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 88px;
  height: 88px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-alt);
}

.color-editor-controls {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.color-exact {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.color-exact-picker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}

.color-exact-picker input[type="color"] {
  width: 38px;
  height: 30px;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  cursor: pointer;
}

.color-exact-hex {
  width: 110px;
  text-transform: uppercase;
}

@media (max-width: 480px) {
  .color-editor {
    align-items: flex-start;
  }
  .color-preview {
    width: 64px;
    height: 64px;
  }
}

.qty-negative {
  color: var(--danger);
  font-weight: 700;
}

.pending-cost-hint {
  margin-top: 4px;
  color: var(--danger);
}

.restock-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  font-size: 0.88rem;
}

.restock-preview > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
</style>
