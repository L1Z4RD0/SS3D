<script setup>
defineProps({
  title: { type: String, required: true },
  width: { type: String, default: "560px" },
});
const emit = defineEmits(["close"]);
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal" :style="{ maxWidth: width }">
      <div class="modal-header">
        <h3>{{ title }}</h3>
        <button class="btn btn-icon btn-ghost" @click="emit('close')">
          <slot name="close-icon">✕</slot>
        </button>
      </div>
      <slot />
    </div>
  </div>
</template>
