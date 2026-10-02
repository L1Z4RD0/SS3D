<script setup>
import { computed, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { markReleaseSeen } from "../api/auth";
import { LATEST_RELEASE } from "../releaseNotes";
import Modal from "./Modal.vue";

// Ventana de "Novedades": sale una sola vez por usuario y solo con la versión más reciente
// (lo visto se guarda en su cuenta, así no se repite en otro dispositivo).
const auth = useAuthStore();
const dismissed = ref(false);

const visible = computed(
  () => !!LATEST_RELEASE && !!auth.user && !dismissed.value && auth.user.last_seen_release !== LATEST_RELEASE.id
);

async function close() {
  dismissed.value = true;
  if (auth.user) auth.user.last_seen_release = LATEST_RELEASE.id;
  try {
    await markReleaseSeen(LATEST_RELEASE.id);
  } catch {
    // Si falla, volverá a salir la próxima vez: mejor eso que perder el aviso.
  }
}
</script>

<template>
  <Modal v-if="visible" :title="LATEST_RELEASE.title" :subtitle="`Novedades · ${LATEST_RELEASE.date}`" width="480px" @close="close">
    <template #icon>
      <img class="whats-new-logo" src="/img/LogoZola.png" alt="" />
    </template>
    <ul class="whats-new-list">
      <li v-for="item in LATEST_RELEASE.items" :key="item.title">
        <span class="whats-new-icon" aria-hidden="true">{{ item.icon }}</span>
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.text }}</p>
        </div>
      </li>
    </ul>
    <div class="whats-new-footer">
      <button type="button" class="btn btn-primary" @click="close">Entendido</button>
    </div>
  </Modal>
</template>

<style scoped>
.whats-new-logo {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  flex-shrink: 0;
}

.whats-new-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.whats-new-list li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.whats-new-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 9px;
  background: var(--surface-alt);
  font-size: 1rem;
}

.whats-new-list strong {
  font-size: 0.92rem;
}

.whats-new-list p {
  margin: 2px 0 0;
  color: var(--text-muted);
  font-size: 0.85rem;
  line-height: 1.45;
}

.whats-new-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}
</style>
