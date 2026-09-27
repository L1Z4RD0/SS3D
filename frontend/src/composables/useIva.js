import { computed } from "vue";
import { useAuthStore } from "../stores/auth";

// Debe coincidir con IVA_PERCENT de backend/app/constants.py.
export const IVA_PERCENT = 19;

/* Beta: el IVA viene apagado y el administrador lo activa por usuario. Apagado, los
   cálculos usan 0% y la interfaz oculta todo lo relacionado con IVA; la lógica se
   conserva para encenderlo en la versión final sin reescribir nada. */
export function useIva() {
  const auth = useAuthStore();
  const ivaEnabled = computed(() => !!auth.user?.iva_enabled);
  const ivaRate = computed(() => (ivaEnabled.value ? IVA_PERCENT / 100 : 0));
  return { ivaEnabled, ivaRate };
}
