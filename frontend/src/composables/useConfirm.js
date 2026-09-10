import { reactive } from "vue";

const state = reactive({
  visible: false,
  title: "",
  message: "",
  confirmLabel: "Confirmar",
  cancelLabel: "Cancelar",
  danger: false,
  resolver: null,
});

export function confirmAction({
  title = "¿Confirmar?",
  message = "",
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  danger = false,
} = {}) {
  state.title = title;
  state.message = message;
  state.confirmLabel = confirmLabel;
  state.cancelLabel = cancelLabel;
  state.danger = danger;
  state.visible = true;
  return new Promise((resolve) => {
    state.resolver = resolve;
  });
}

export function useConfirmState() {
  function resolve(value) {
    state.visible = false;
    state.resolver?.(value);
    state.resolver = null;
  }
  return { state, resolve };
}
