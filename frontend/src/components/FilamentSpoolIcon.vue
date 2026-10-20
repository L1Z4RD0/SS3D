<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  color: { type: String, required: true },
  size: { type: [Number, String], default: 40 },
});

/* Pinta la foto real del carrete (public/img/FilamentoIMG.png: filamento blanco, bobina negra,
   fondo transparente) del color del filamento. Antes se hacía con máscara CSS + mix-blend-mode,
   que algunos navegadores (Safari/iOS, Android antiguos) no dibujaban o dibujaban mal. Ahora
   la foto se carga UNA vez y se tiñe en un canvas: cada píxel se multiplica por el color según
   lo claro que es (el filamento blanco toma el color, la bobina negra queda igual). Cada color
   se calcula una sola vez y se reutiliza. Mientras carga, o si la foto no se pudiera cargar,
   se muestra un círculo del color, nunca un espacio vacío. */
const SRC = "/img/FilamentoIMG.png";
let basePromise = null;
const tinted = new Map();

function loadBase() {
  if (!basePromise) {
    basePromise = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0);
        resolve(ctx.getImageData(0, 0, canvas.width, canvas.height));
      };
      img.onerror = reject;
      img.src = SRC;
    }).catch((err) => {
      basePromise = null; // se reintenta la próxima vez que se pida
      throw err;
    });
  }
  return basePromise;
}

function parseHex(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

async function tint(hex) {
  const key = hex.toLowerCase();
  if (tinted.has(key)) return tinted.get(key);
  const base = await loadBase();
  const rgb = parseHex(key);
  const out = new ImageData(new Uint8ClampedArray(base.data), base.width, base.height);
  const d = out.data;
  for (let i = 0; i < d.length; i += 4) {
    if (!d[i + 3]) continue;
    const lum = (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) / 255;
    for (let c = 0; c < 3; c++) d[i + c] = d[i + c] * (1 - lum + (lum * rgb[c]) / 255);
  }
  const canvas = document.createElement("canvas");
  canvas.width = base.width;
  canvas.height = base.height;
  canvas.getContext("2d").putImageData(out, 0, 0);
  const url = canvas.toDataURL("image/png");
  tinted.set(key, url);
  return url;
}

const src = ref(null);
watch(
  () => props.color,
  async (color) => {
    const hex = parseHex(color) ? color : null;
    src.value = hex ? tinted.get(hex.toLowerCase()) || null : null;
    if (!hex || src.value) return;
    try {
      const url = await tint(hex);
      if (props.color === color) src.value = url;
    } catch {
      // Sin foto: queda el círculo del color.
    }
  },
  { immediate: true }
);
</script>

<template>
  <div
    class="spool-icon"
    :style="{ width: typeof size === 'number' ? size + 'px' : size, height: typeof size === 'number' ? size + 'px' : size }"
  >
    <img v-if="src" class="spool-img" :src="src" alt="" />
    <span v-else class="spool-fallback" :style="{ background: color }"></span>
  </div>
</template>

<style scoped>
.spool-icon {
  position: relative;
  flex-shrink: 0;
  display: grid;
  place-items: center;
}

.spool-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.spool-fallback {
  width: 70%;
  height: 70%;
  border-radius: 50%;
  border: 3px solid #2a2a2a;
  box-shadow: inset 0 0 0 4px rgba(255, 255, 255, 0.25);
}
</style>
