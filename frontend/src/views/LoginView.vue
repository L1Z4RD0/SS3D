<script setup>
import { ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "../stores/auth";

const username = ref("");
const password = ref("");
const submitting = ref(false);
const errorMessage = ref("");

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

async function handleSubmit() {
  errorMessage.value = "";
  submitting.value = true;
  try {
    await auth.login(username.value.trim(), password.value);
    router.push(route.query.redirect || { name: "dashboard" });
  } catch (err) {
    const status = err.response?.status;
    if (status === 423) {
      errorMessage.value = err.response?.data?.detail || "Cuenta bloqueada temporalmente.";
    } else if (status === 403) {
      errorMessage.value = "Esta cuenta está desactivada.";
    } else {
      errorMessage.value = err.response?.data?.detail || "Usuario o contraseña incorrectos.";
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-panel">
      <div class="login-brand">
        <div class="brand-mark">Z</div>
        <span>Zola</span>
      </div>
      <p class="login-tagline">Gestión integral para tu negocio de impresión 3D</p>

      <form class="login-form" @submit.prevent="handleSubmit">
        <div class="field">
          <label for="username">Usuario</label>
          <input id="username" v-model="username" type="text" autocomplete="username" required autofocus />
        </div>
        <div class="field">
          <label for="password">Contraseña</label>
          <input id="password" v-model="password" type="password" autocomplete="current-password" required />
        </div>

        <div v-if="errorMessage" class="alert alert-danger">{{ errorMessage }}</div>

        <button class="btn btn-primary w-full" type="submit" :disabled="submitting" style="margin-top: 6px; padding: 11px">
          <span v-if="submitting" class="spinner" />
          {{ submitting ? "Ingresando..." : "Iniciar sesión" }}
        </button>
      </form>
    </div>
    <div class="login-side">
      <div class="login-side-content">
        <h2>Controla costos, márgenes e inventario en un solo lugar</h2>
        <p>Calculadora de precios, registro de ventas, inventario de filamentos e insumos, e impresoras — todo conectado.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(360px, 480px) 1fr;
  background: var(--bg);
}

.login-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 48px 56px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 800;
  font-size: 1.4rem;
  margin-bottom: 6px;
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
}

.login-tagline {
  color: var(--text-muted);
  margin-bottom: 32px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.login-side {
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, var(--sidebar-bg), #2a2450 120%);
  padding: 48px;
}

.login-side-content {
  max-width: 420px;
  color: #fff;
}

.login-side-content h2 {
  font-size: 1.7rem;
  line-height: 1.3;
  margin-bottom: 14px;
}

.login-side-content p {
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.6;
}

@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .login-side {
    display: none;
  }
  .login-panel {
    padding: 40px 24px;
  }
}
</style>
