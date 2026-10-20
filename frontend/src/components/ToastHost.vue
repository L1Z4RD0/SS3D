<script setup>
import { nextTick, ref, watch } from "vue";
import { useToast } from "../composables/useToast";
import { prefersReducedMotion } from "../composables/useMotion";

const { current } = useToast();
const box = ref(null);
const COLORS = ["#5b4bf5", "#17b3a3", "#8a5cf6", "#c8871a", "#3fd8c6"];

// Confeti: unos cuadraditos que salen del ícono y se desvanecen (Web Animations API).
function confetti() {
  if (prefersReducedMotion() || !box.value?.animate) return;
  const r = box.value.getBoundingClientRect();
  for (let i = 0; i < 18; i++) {
    const piece = document.createElement("i");
    piece.className = "toast-confetti";
    piece.style.background = COLORS[i % COLORS.length];
    piece.style.left = `${r.left + 22}px`;
    piece.style.top = `${r.top + 14}px`;
    document.body.appendChild(piece);
    const angle = Math.random() * Math.PI - Math.PI;
    const dist = 80 + Math.random() * 90;
    piece.animate(
      [
        { transform: "translate(0, 0) rotate(0)", opacity: 1 },
        {
          transform: `translate(${Math.cos(angle) * dist}px, ${Math.sin(angle) * dist - 30}px) rotate(${Math.random() * 540}deg)`,
          opacity: 0,
        },
      ],
      { duration: 900 + Math.random() * 400, easing: "cubic-bezier(.22,1,.36,1)" }
    ).onfinish = () => piece.remove();
  }
}

watch(
  () => current.value?.id,
  async () => {
    if (!current.value?.celebrate) return;
    await nextTick();
    // Espera a que el aviso termine de subir para que el confeti salga desde su lugar.
    setTimeout(confetti, 250);
  }
);
</script>

<template>
  <Transition name="toast">
    <div v-if="current" :key="current.id" ref="box" class="toast" role="status">
      <svg class="toast-check" viewBox="0 0 30 30" aria-hidden="true">
        <circle cx="15" cy="15" r="15" />
        <path pathLength="1" d="M9 15.5l4 4 8-8.5" />
      </svg>
      <div>
        <strong>{{ current.title }}</strong>
        <div v-if="current.detail" class="toast-detail">{{ current.detail }}</div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.toast {
  position: fixed;
  z-index: 300;
  right: 24px;
  bottom: 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: min(380px, calc(100vw - 32px));
  padding: 12px 18px 12px 12px;
  border-radius: 14px;
  background: #1b1d2b;
  color: #fff;
  box-shadow: var(--shadow-lg);
  font-size: 0.9rem;
}

.toast-detail {
  font-size: 0.8rem;
  opacity: 0.72;
}

.toast-check {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
}

.toast-check circle {
  fill: var(--success);
  transform-origin: center;
  animation: zola-pop-in 0.45s var(--ease-spring) 0.1s both;
}

.toast-check path {
  fill: none;
  stroke: #fff;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  animation: zola-draw 0.45s var(--ease-out) 0.4s forwards;
}

.toast-enter-active {
  transition: transform 0.5s var(--ease-spring), opacity 0.3s;
}
.toast-leave-active {
  transition: transform 0.25s ease, opacity 0.25s;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(30px) scale(0.9);
}

@media (max-width: 640px) {
  .toast {
    left: 16px;
    right: 16px;
    max-width: none;
    bottom: calc(96px + env(safe-area-inset-bottom));
  }
}
</style>

<style>
.toast-confetti {
  position: fixed;
  z-index: 301;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  pointer-events: none;
}
</style>
