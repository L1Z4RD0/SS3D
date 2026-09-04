<script setup>
import { useRouter } from "vue-router";
const router = useRouter();
</script>

<template>
  <div class="empty-state" style="min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center">
    <h3 style="font-size: 1.6rem">404</h3>
    <p>Esta página no existe.</p>
    <button class="btn btn-primary mt-4" @click="router.push('/')">Volver al inicio</button>
  </div>
</template>
