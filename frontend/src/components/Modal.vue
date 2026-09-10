<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "" },
  width: { type: String, default: "560px" },
});
const emit = defineEmits(["close"]);
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal" :style="{ maxWidth: width }">
      <div class="modal-header">
        <div class="flex items-center gap-3" style="min-width: 0">
          <slot name="icon" />
          <div style="min-width: 0">
            <h3>{{ title }}</h3>
            <p v-if="subtitle" class="modal-subtitle">{{ subtitle }}</p>
          </div>
        </div>
        <button class="btn btn-icon btn-ghost" @click="emit('close')" style="flex-shrink: 0">
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
