<script setup>
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "" },
  width: { type: String, default: "560px" },
  // Formularios donde se escriben datos: el clic en el fondo no los cierra (solo la ✕ o
  // Cancelar), para no perder lo ingresado por un clic de más.
  persistent: { type: Boolean, default: false },
});
const emit = defineEmits(["close"]);

// El navegador cuenta como "clic en el fondo" arrastrar desde un campo (ej. al seleccionar
// texto) y soltar fuera de la ventana. Solo se cierra si el clic también EMPEZÓ en el fondo.
let pressedOnBackdrop = false;
function onBackdropDown(event) {
  pressedOnBackdrop = event.target === event.currentTarget;
}
function onBackdropClick(event) {
  const startedAndEndedOnBackdrop = pressedOnBackdrop && event.target === event.currentTarget;
  pressedOnBackdrop = false;
  if (startedAndEndedOnBackdrop && !props.persistent) emit("close");
}
</script>

<template>
  <div class="modal-backdrop" @mousedown="onBackdropDown" @click="onBackdropClick">
    <div class="modal" :style="{ maxWidth: width }">
      <div class="modal-header">
        <div class="flex items-center gap-3" style="min-width: 0">
          <slot name="icon" />
          <div style="min-width: 0">
            <h3>{{ title }}</h3>
            <p v-if="subtitle" class="modal-subtitle">{{ subtitle }}</p>
          </div>
        </div>
        <button type="button" class="btn btn-icon btn-ghost" @click="emit('close')" style="flex-shrink: 0">
          <slot name="close-icon">✕</slot>
        </button>
      </div>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.modal-subtitle {
  margin: 2px 0 0;
  font-size: 0.82rem;
  color: var(--text-muted);
  font-weight: 400;
}
</style>
