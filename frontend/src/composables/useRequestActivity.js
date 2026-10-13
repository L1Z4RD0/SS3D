import { ref } from "vue";

// Cuántas peticiones a la API hay en curso. Lo usa la barra fina de la parte superior
// para indicar que se está actualizando sin ocultar los datos de la pantalla.
const pending = ref(0);

export function requestStarted() {
  pending.value += 1;
}

export function requestFinished() {
  pending.value = Math.max(0, pending.value - 1);
}

export function useRequestActivity() {
  return { pending };
}
