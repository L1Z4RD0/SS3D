<script setup>
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "./stores/auth";
import AppSidebar from "./components/AppSidebar.vue";
import AppTopbar from "./components/AppTopbar.vue";
import AssistantBubble from "./components/AssistantBubble.vue";
import ConfirmDialogHost from "./components/ConfirmDialogHost.vue";
import MobileTabBar from "./components/MobileTabBar.vue";
import ToastHost from "./components/ToastHost.vue";
import SupplyDebtBanner from "./components/SupplyDebtBanner.vue";
import WhatsNewModal from "./components/WhatsNewModal.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const showShell = computed(() => auth.isAuthenticated && !route.meta.public);

// Si la sesión termina con la app abierta (refresh rechazado), el guard del router no se
// vuelve a ejecutar: sin esto la vista quedaba sin barra lateral ni encabezado hasta que el
// usuario recargaba. Se lo lleva al login, conservando a dónde volver.
watch(
  () => auth.isAuthenticated,
  (isAuthenticated) => {
    if (!isAuthenticated && !route.meta.public) {
      router.replace({ name: "login", query: { redirect: route.fullPath } });
    }
  }
);
</script>

<template>
  <div v-if="showShell" class="app-shell">
    <AppSidebar />
    <div class="app-main">
      <!-- Fondo de colores de la marca que se mueve lento detrás del encabezado -->
      <div class="aurora" aria-hidden="true"><i></i><i></i><i></i></div>
      <AppTopbar />
      <div class="app-content">
        <SupplyDebtBanner />
        <router-view v-slot="{ Component, route: current }">
          <Transition name="page">
            <component :is="Component" :key="current.path" />
          </Transition>
        </router-view>
      </div>
    </div>
    <MobileTabBar />
    <AssistantBubble />
  </div>
  <router-view v-else />
  <WhatsNewModal v-if="showShell" />
  <ConfirmDialogHost />
  <ToastHost />
</template>
