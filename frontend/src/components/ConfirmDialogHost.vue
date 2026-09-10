<script setup>
import { useConfirmState } from "../composables/useConfirm";

const { state, resolve } = useConfirmState();
</script>

<template>
  <div v-if="state.visible" class="modal-backdrop" @click.self="resolve(false)">
    <div class="modal" style="max-width: 400px">
      <h3>{{ state.title }}</h3>
      <p class="text-muted mt-2" style="line-height: 1.5">{{ state.message }}</p>
      <div class="form-actions">
        <button class="btn btn-secondary" @click="resolve(false)">{{ state.cancelLabel }}</button>
        <button :class="['btn', state.danger ? 'btn-danger' : 'btn-primary']" @click="resolve(true)">
          {{ state.confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
