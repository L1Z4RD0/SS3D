<script setup>
import { ref } from "vue";
import Icon from "./Icon.vue";

// Campo de contraseña con botón para mostrarla u ocultarla. Los atributos (id,
// autocomplete, required, minlength...) pasan directo al <input>.
defineOptions({ inheritAttrs: false });
const model = defineModel({ type: String, default: "" });
const visible = ref(false);
</script>

<template>
  <div class="password-input">
    <input v-model="model" v-bind="$attrs" :type="visible ? 'text' : 'password'" />
    <button
      type="button"
      class="password-toggle"
      :aria-label="visible ? 'Ocultar contraseña' : 'Mostrar contraseña'"
      :title="visible ? 'Ocultar contraseña' : 'Mostrar contraseña'"
      @click="visible = !visible"
    >
      <Icon :name="visible ? 'eyeOff' : 'eye'" :size="18" />
    </button>
  </div>
</template>

<style scoped>
.password-input {
  position: relative;
  width: 100%;
}

.password-input input {
  width: 100%;
  padding-right: 42px;
}

.password-toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.password-toggle:hover {
  color: var(--text);
  background: var(--surface-alt);
}
</style>
