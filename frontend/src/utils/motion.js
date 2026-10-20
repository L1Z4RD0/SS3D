/* Ayudas de animación compartidas (estilos en assets/motion.css). */

// v-reveal: el elemento aparece (sube y se aclara) cuando entra en pantalla al bajar.
// v-reveal="0.1" agrega un retraso en segundos para que varias tarjetas entren en cascada.
// Sin IntersectionObserver se muestra directo.
let observer = null;
function getObserver() {
  if (observer || typeof IntersectionObserver === "undefined") return observer;
  observer = new IntersectionObserver(
    (entries) =>
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("in");
        observer.unobserve(entry.target);
      }),
    { threshold: 0.12 }
  );
  return observer;
}

export const reveal = {
  mounted(el, binding) {
    const io = getObserver();
    if (!io) return;
    el.classList.add("reveal");
    if (binding.value) el.style.setProperty("--reveal-delay", `${binding.value}s`);
    io.observe(el);
  },
  unmounted(el) {
    observer?.unobserve(el);
  },
};

// Luz que sigue al mouse en los elementos con clase .glow: un solo listener para toda la
// app que actualiza la posición (--mx, --my) en el elemento bajo el cursor.
export function trackGlow() {
  if (!window.matchMedia?.("(hover: hover)").matches) return;
  document.addEventListener(
    "pointermove",
    (event) => {
      const el = event.target.closest?.(".glow");
      if (!el) return;
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${event.clientX - r.left}px`);
      el.style.setProperty("--my", `${event.clientY - r.top}px`);
    },
    { passive: true }
  );
}

// Curva suave que pasa por los valores (para los mini gráficos). Devuelve el "d" del
// trazo y el último punto, dentro de una caja de ancho w y alto h.
export function sparkPath(values, w, h, pad = 4) {
  const nums = values.map(Number);
  if (nums.length < 2) return null;
  const max = Math.max(...nums);
  const min = Math.min(...nums);
  const pts = nums.map((v, i) => [
    (i / (nums.length - 1)) * w,
    h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2),
  ]);
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const cx = ((x0 + x1) / 2).toFixed(1);
    d += ` C${cx},${y0.toFixed(1)} ${cx},${y1.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return { d, last: pts[pts.length - 1] };
}

// Llama a cb la primera vez que el elemento se ve en pantalla (o de inmediato si el
// navegador no sabe detectarlo). Devuelve una función para dejar de observar.
export function whenVisible(el, cb) {
  if (!el || typeof IntersectionObserver === "undefined") {
    cb();
    return () => {};
  }
  const io = new IntersectionObserver(
    (entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      io.disconnect();
      cb();
    },
    { threshold: 0.25 }
  );
  io.observe(el);
  return () => io.disconnect();
}
