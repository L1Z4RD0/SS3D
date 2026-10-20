import { ref, watchEffect } from "vue";

// Preferencia "Movimiento: completo / reducido" (botón de la barra superior). Con "reducido"
// se pone la clase .reduced-motion en <html> y motion.css apaga las animaciones, igual que
// cuando el sistema pide reducir movimiento.
const STORAGE_KEY = "zola-motion";
const readStored = () => {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};
const motion = ref(readStored() === "reduced" ? "reduced" : "full");

watchEffect(() => {
  document.documentElement.classList.toggle("reduced-motion", motion.value === "reduced");
  try {
    localStorage.setItem(STORAGE_KEY, motion.value);
  } catch {
    // Sin almacenamiento (modo privado) la preferencia dura solo esta sesión.
  }
});

// true si no hay que animar: por el botón o por la configuración del sistema.
export function prefersReducedMotion() {
  return motion.value === "reduced" || !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

export function useMotion() {
  function toggle() {
    motion.value = motion.value === "reduced" ? "full" : "reduced";
  }
  return { motion, toggle };
}
