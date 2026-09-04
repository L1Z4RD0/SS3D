<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useAuthStore } from "./stores/auth";
import AppSidebar from "./components/AppSidebar.vue";
import AppTopbar from "./components/AppTopbar.vue";
import ConfirmDialogHost from "./components/ConfirmDialogHost.vue";

const route = useRoute();
const auth = useAuthStore();

const showShell = computed(() => auth.isAuthenticated && !route.meta.public);
</script>

<template>
  <div v-if="showShell" class="app-shell">
    <AppSidebar />
    <div class="app-main">
      <AppTopbar />
      <div class="app-content">
        <router-view />
      </div>
    </div>
  </div>
  <router-view v-else />
  <ConfirmDialogHost />
</template>
