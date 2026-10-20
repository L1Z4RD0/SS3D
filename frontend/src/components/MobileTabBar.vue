<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useMobileNav } from "../composables/useMobileNav";
import Icon from "./Icon.vue";

// Barra de navegación inferior (solo celular): accesos a mano del pulgar y botón + para
// registrar una venta. "Más" abre el menú lateral completo de siempre.
const route = useRoute();
const router = useRouter();
const mobileNav = useMobileNav();

const tabs = [
  { to: "/dashboard", label: "Inicio", icon: "dashboard" },
  { to: "/ventas", label: "Ventas", icon: "sales" },
  { fab: true },
  { to: "/calendario", label: "Agenda", icon: "calendar" },
  { more: true, label: "Más", icon: "menu" },
];

const activeIndex = computed(() => {
  if (mobileNav.isOpen.value) return 4;
  const i = tabs.findIndex((t) => t.to && route.path.startsWith(t.to));
  return i === -1 ? 4 : i;
});

// Fondo del ítem activo que se desliza de uno a otro.
const bar = ref(null);
const pill = ref({ left: 0, visible: false });
function movePill() {
  const el = bar.value?.querySelectorAll(".tab-slot")[activeIndex.value];
  if (!el) return;
  pill.value = { left: el.offsetLeft + (el.offsetWidth - 60) / 2, visible: true };
}
watch(activeIndex, () => nextTick(movePill));
onMounted(() => {
  nextTick(movePill);
  window.addEventListener("resize", movePill);
});
onBeforeUnmount(() => window.removeEventListener("resize", movePill));

function newSale() {
  mobileNav.close();
  router.push({ path: "/ventas", query: { nueva: "1" } });
}
</script>

<template>
  <nav ref="bar" class="tabbar" aria-label="Navegación principal">
    <div class="tab-pill" :class="{ visible: pill.visible }" :style="{ transform: `translateX(${pill.left}px)` }"></div>
    <template v-for="(tab, i) in tabs" :key="i">
      <div v-if="tab.fab" class="tab-slot tab-fab">
        <button type="button" aria-label="Nueva venta" @click="newSale">
          <Icon name="plus" :size="26" />
        </button>
      </div>
      <button
        v-else-if="tab.more"
        type="button"
        class="tab-slot tab-item"
        :class="{ active: activeIndex === i }"
        @click="mobileNav.toggle()"
      >
        <Icon :name="tab.icon" :size="22" />
        <span>{{ tab.label }}</span>
      </button>
      <router-link
        v-else
        :to="tab.to"
        class="tab-slot tab-item"
        :class="{ active: activeIndex === i }"
        @click="mobileNav.close()"
      >
        <Icon :name="tab.icon" :size="22" />
        <span>{{ tab.label }}</span>
      </router-link>
    </template>
  </nav>
</template>

<style scoped>
.tabbar {
  display: none;
}

@media (max-width: 640px) {
  .tabbar {
    display: flex;
    align-items: center;
    position: fixed;
    z-index: 90; /* bajo las ventanas (100) y el menú lateral (200) */
    left: 12px;
    right: 12px;
    bottom: calc(12px + env(safe-area-inset-bottom));
    height: 66px;
    padding: 0 6px;
    border-radius: 22px;
    background: rgba(23, 24, 43, 0.9);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    box-shadow: 0 14px 34px rgba(20, 20, 43, 0.35);
  }
}

.tab-pill {
  position: absolute;
  top: 9px;
  left: 0;
  width: 60px;
  height: 48px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.1);
  opacity: 0;
  transition: transform 0.45s var(--ease-spring), opacity 0.2s;
}
.tab-pill.visible {
  opacity: 1;
}

.tab-slot {
  flex: 1;
  min-width: 0;
}

.tab-item {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: 0;
  background: none;
  color: #9598bd;
  font: inherit;
  font-size: 0.68rem;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: color 0.25s;
  -webkit-tap-highlight-color: transparent;
}

.tab-item svg {
  transition: transform 0.4s var(--ease-spring);
}

.tab-item.active {
  color: #fff;
}

.tab-item.active svg {
  transform: translateY(-2px) scale(1.12);
}

.tab-fab {
  flex: 0 0 64px;
  display: grid;
  place-items: center;
}

.tab-fab button {
  width: 56px;
  height: 56px;
  margin-top: -30px;
  display: grid;
  place-items: center;
  border: 4px solid var(--bg);
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  box-shadow: 0 10px 22px rgba(91, 75, 245, 0.45);
  cursor: pointer;
  transition: transform 0.3s var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}

.tab-fab button:active {
  transform: scale(0.9) rotate(90deg);
}
</style>
