<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import * as adminApi from "../api/admin";
import { formatDateTime } from "../utils/format";
import { confirmAction } from "../composables/useConfirm";
import Modal from "../components/Modal.vue";
import Icon from "../components/Icon.vue";

const tab = ref("users");

/* -------- Users -------- */
const users = ref([]);
const loadingUsers = ref(true);
const showUserModal = ref(false);
const userSaving = ref(false);
const userError = ref("");
const userForm = reactive({ username: "", password: "", role: "user" });

async function loadUsers() {
  loadingUsers.value = true;
  try {
    users.value = await adminApi.listUsers();
  } finally {
    loadingUsers.value = false;
  }
}

function openCreateUser() {
  Object.assign(userForm, { username: "", password: "", role: "user" });
  userError.value = "";
  showUserModal.value = true;
}

async function submitUser() {
  userSaving.value = true;
  userError.value = "";
  try {
    await adminApi.createUser(userForm);
    showUserModal.value = false;
    await loadUsers();
  } catch (err) {
    userError.value = err.response?.data?.detail || "No se pudo crear el usuario";
  } finally {
    userSaving.value = false;
  }
}

async function toggleUser(user) {
  const activating = !user.is_active;
  const ok = await confirmAction({
    title: activating ? "Reactivar usuario" : "Desactivar usuario",
    message: activating
      ? `¿Reactivar a "${user.username}"? Podrá volver a iniciar sesión.`
      : `¿Desactivar a "${user.username}"? No podrá iniciar sesión, pero sus datos se conservan.`,
    confirmLabel: activating ? "Reactivar" : "Desactivar",
    danger: !activating,
  });
  if (!ok) return;
  if (activating) {
    await adminApi.reactivateUser(user.id);
  } else {
    await adminApi.deactivateUser(user.id);
  }
  await loadUsers();
}

/* -------- Audit logs -------- */
const logs = ref([]);
const logsTotal = ref(0);
const loadingLogs = ref(true);
const logLimit = 30;
const logOffset = ref(0);
const logFilters = reactive({ user_id: "", event_type: "", date_from: "", date_to: "" });

async function loadLogs() {
  loadingLogs.value = true;
  try {
    const params = { limit: logLimit, offset: logOffset.value };
    Object.entries(logFilters).forEach(([k, v]) => {
      if (v) params[k] = v;
    });
    const page = await adminApi.listAuditLogs(params);
    logs.value = page.items;
    logsTotal.value = page.total;
  } finally {
    loadingLogs.value = false;
  }
}

function applyLogFilters() {
  logOffset.value = 0;
  loadLogs();
}
function resetLogFilters() {
  Object.assign(logFilters, { user_id: "", event_type: "", date_from: "", date_to: "" });
  applyLogFilters();
}
function nextLogPage() {
  if (logOffset.value + logLimit < logsTotal.value) {
    logOffset.value += logLimit;
    loadLogs();
  }
}
function prevLogPage() {
  if (logOffset.value > 0) {
    logOffset.value = Math.max(0, logOffset.value - logLimit);
    loadLogs();
  }
}

const eventBadge = (eventType) => {
  if (eventType.includes("FAILED") || eventType.includes("LOCKED") || eventType.includes("DELETED") || eventType.includes("DEACTIVATED")) return "badge-danger";
  if (eventType.includes("SUCCESS") || eventType.includes("CREATED") || eventType.includes("REACTIVATED")) return "badge-success";
  if (eventType.includes("UPDATED")) return "badge-info";
  return "badge-neutral";
};

const logPageLabel = computed(() => {
  if (!logsTotal.value) return "0 resultados";
  const from = logOffset.value + 1;
  const to = Math.min(logOffset.value + logLimit, logsTotal.value);
  return `${from}-${to} de ${logsTotal.value}`;
});

onMounted(() => {
  loadUsers();
  loadLogs();
});
</script>

<template>
  <div>
    <div class="page-header">
      <p class="page-subtitle">Gestión de usuarios y auditoría del sistema</p>
    </div>

    <div class="tabs">
      <button class="tab-btn" :class="{ active: tab === 'users' }" @click="tab = 'users'">Usuarios</button>
      <button class="tab-btn" :class="{ active: tab === 'logs' }" @click="tab = 'logs'">Auditoría</button>
    </div>

    <div v-if="tab === 'users'" class="card">
      <div class="card-header">
        <h3>Usuarios</h3>
        <button class="btn btn-primary btn-sm" @click="openCreateUser">
          <Icon name="plus" :size="15" /> Nuevo usuario
        </button>
      </div>

      <div v-if="loadingUsers" class="empty-state">Cargando...</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Rol</th>
              <th>Estado</th>
              <th>Intentos fallidos</th>
              <th>Bloqueado hasta</th>
              <th>Creado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td><strong>{{ u.username }}</strong></td>
              <td><span class="badge badge-neutral">{{ u.role === "admin" ? "Administrador" : "Usuario" }}</span></td>
              <td>
                <span class="badge" :class="u.is_active ? 'badge-success' : 'badge-danger'">
                  {{ u.is_active ? "Activo" : "Desactivado" }}
                </span>
              </td>
              <td class="text-right mono">{{ u.failed_login_attempts }}</td>
              <td>{{ u.locked_until ? formatDateTime(u.locked_until) : "-" }}</td>
              <td>{{ formatDateTime(u.created_at) }}</td>
              <td class="text-right">
                <button
                  class="btn btn-sm"
                  :class="u.is_active ? 'btn-danger' : 'btn-secondary'"
                  @click="toggleUser(u)"
                >
                  {{ u.is_active ? "Desactivar" : "Reactivar" }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else class="card">
      <div class="card-header">
        <h3>Registro de auditoría</h3>
      </div>

      <div class="grid grid-cols-4 mt-2" style="margin-bottom: 16px">
        <div class="field">
          <label>Usuario</label>
          <select v-model="logFilters.user_id">
            <option value="">Todos</option>
            <option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option>
          </select>
        </div>
        <div class="field">
          <label>Tipo de evento</label>
          <input v-model="logFilters.event_type" placeholder="Ej: LOGIN_FAILED" />
        </div>
        <div class="field">
          <label>Desde</label>
          <input v-model="logFilters.date_from" type="date" />
        </div>
        <div class="field">
          <label>Hasta</label>
          <input v-model="logFilters.date_to" type="date" />
        </div>
      </div>
      <div class="flex gap-2" style="margin-bottom: 16px">
        <button class="btn btn-primary btn-sm" @click="applyLogFilters">Filtrar</button>
        <button class="btn btn-secondary btn-sm" @click="resetLogFilters">Limpiar</button>
      </div>

      <div v-if="loadingLogs" class="empty-state">Cargando...</div>
      <div v-else-if="!logs.length" class="empty-state">Sin eventos para este filtro.</div>
      <template v-else>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Usuario</th>
                <th>Evento</th>
                <th>Entidad</th>
                <th>Detalle</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="log in logs" :key="log.id">
                <td class="text-sm">{{ formatDateTime(log.created_at) }}</td>
                <td>{{ log.username || "-" }}</td>
                <td><span class="badge" :class="eventBadge(log.event_type)">{{ log.event_type }}</span></td>
                <td class="text-sm">{{ log.entity_type || "-" }}</td>
                <td class="text-sm text-muted" style="max-width: 260px">
                  <span v-if="log.details">{{ JSON.stringify(log.details) }}</span>
                  <span v-else>-</span>
                </td>
                <td class="text-sm">{{ log.ip_address || "-" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex items-center justify-between mt-4">
          <span class="text-muted text-sm">{{ logPageLabel }}</span>
          <div class="flex gap-2">
            <button class="btn btn-secondary btn-sm" :disabled="logOffset === 0" @click="prevLogPage">Anterior</button>
            <button class="btn btn-secondary btn-sm" :disabled="logOffset + logLimit >= logsTotal" @click="nextLogPage">Siguiente</button>
          </div>
        </div>
      </template>
    </div>

    <Modal v-if="showUserModal" title="Nuevo usuario" @close="showUserModal = false">
      <form @submit.prevent="submitUser">
        <div class="flex flex-col gap-3">
          <div class="field">
            <label>Nombre de usuario</label>
            <input v-model="userForm.username" required minlength="3" />
          </div>
          <div class="field">
            <label>Contraseña inicial</label>
            <input v-model="userForm.password" type="password" required minlength="8" />
            <span class="field-hint">Mínimo 8 caracteres. El usuario podrá cambiarla luego.</span>
          </div>
          <div class="field">
            <label>Rol</label>
            <select v-model="userForm.role">
              <option value="user">Usuario</option>
              <option value="admin">Administrador</option>
            </select>
          </div>
        </div>

        <div v-if="userError" class="alert alert-danger mt-4">{{ userError }}</div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="showUserModal = false">Cancelar</button>
          <button type="submit" class="btn btn-primary" :disabled="userSaving">
            {{ userSaving ? "Creando..." : "Crear usuario" }}
          </button>
        </div>
      </form>
    </Modal>
  </div>
</template>
