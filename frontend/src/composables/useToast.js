import { ref } from "vue";

// Aviso breve abajo a la derecha (en celular, sobre la barra inferior). Lo muestra ToastHost.
// celebrate: suma un poco de confeti (al registrar una venta nueva).
const current = ref(null);
let timer = null;
let seq = 0;

export function showToast(title, { detail = "", celebrate = false, duration = 3000 } = {}) {
  clearTimeout(timer);
  seq += 1;
  current.value = { id: seq, title, detail, celebrate };
  timer = setTimeout(() => (current.value = null), duration);
}

export function useToast() {
  return { current };
}
