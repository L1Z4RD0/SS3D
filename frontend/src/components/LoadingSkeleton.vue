<script setup>
// Primera carga de una pantalla: la forma del contenido con un brillo, en vez del texto
// "Cargando...". Solo aparece mientras todavía no hay datos que mostrar.
defineProps({ lines: { type: Number, default: 4 } });
const widths = ["45%", "100%", "92%", "100%", "78%", "96%", "64%", "88%"];
</script>

<template>
  <div class="skeleton" role="status" aria-label="Cargando">
    <div v-for="i in lines" :key="i" class="skeleton-line" :style="{ width: widths[(i - 1) % widths.length] }"></div>
  </div>
</template>

<style scoped>
.skeleton {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 4px;
}
</style>
