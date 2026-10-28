<script setup>
import { nextTick, onMounted, ref } from "vue";
import { getAssistantAccess, sendAssistantChat } from "../api/assistant";
import { extractApiError } from "../utils/validation";
import Icon from "./Icon.vue";

// Burbuja del asistente IA: solo aparece para las cuentas del emprendimiento. La
// conversación vive en memoria mientras la sesión esté abierta (se borra al salir).
const enabled = ref(false);
const open = ref(false);
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const error = ref("");
const listEl = ref(null);
const inputEl = ref(null);

const SUGGESTIONS = [
  "¿Cuánto vendimos este mes y cuánto ganamos?",
  "¿Quiénes son nuestros mejores clientes?",
  "¿Qué pedidos están pendientes o atrasados?",
  "¿Qué filamentos están por acabarse?",
];

onMounted(async () => {
  try {
    enabled.value = (await getAssistantAccess()).enabled;
  } catch {
    // Si falla, simplemente no se muestra la burbuja.
  }
});

async function scrollToEnd() {
  await nextTick();
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight;
}

async function toggle() {
  open.value = !open.value;
  if (open.value) {
    await scrollToEnd();
    inputEl.value?.focus();
  }
}

async function send(text = draft.value) {
  text = text.trim();
  if (!text || sending.value) return;
  error.value = "";
  messages.value.push({ role: "user", text });
  draft.value = "";
  sending.value = true;
  scrollToEnd();
  try {
    const reply = await sendAssistantChat(messages.value);
    messages.value.push({ role: "assistant", text: reply });
  } catch (err) {
    // La pregunta sin respuesta se quita (Gemini exige que se alternen) y vuelve al cuadro.
    messages.value.pop();
    draft.value = text;
    error.value = extractApiError(err, "No se pudo obtener respuesta.");
  } finally {
    sending.value = false;
    scrollToEnd();
    inputEl.value?.focus();
  }
}

function onKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}

function clearChat() {
  messages.value = [];
  error.value = "";
}

// Markdown mínimo (negrita, cursiva, código, listas, tablas). Se escapa el HTML ANTES de
// dar formato, así nada de lo que responda el modelo se ejecuta como HTML.
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function inline(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
}

function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  const html = [];
  let list = null;
  let table = [];

  const closeList = () => {
    if (list) html.push(`</${list}>`);
    list = null;
  };
  const closeTable = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\|?[\s:|-]+\|?$/.test(r));
    const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));
    const [head, ...body] = rows;
    html.push(
      `<div class="md-table"><table><thead><tr>${cells(head).map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
        body.map((r) => `<tr>${cells(r).map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") +
        "</tbody></table></div>"
    );
    table = [];
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("|")) {
      closeList();
      table.push(line);
      continue;
    }
    closeTable();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      if (list !== kind) {
        closeList();
        html.push(`<${kind}>`);
        list = kind;
      }
      html.push(`<li>${inline((bullet || numbered)[1])}</li>`);
    } else {
      closeList();
      if (heading) html.push(`<p><strong>${inline(heading[1])}</strong></p>`);
      else if (line) html.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList();
  closeTable();
  return html.join("");
}
</script>

<template>
  <template v-if="enabled">
    <Transition name="assistant-panel">
      <section v-if="open" class="assistant-panel" role="dialog" aria-label="Asistente Zola">
        <header class="assistant-header">
          <span class="assistant-avatar"><Icon name="sparkle" :size="18" /></span>
          <div class="assistant-title">
            <strong>Asistente Zola</strong>
            <small>Consultas sobre ventas, clientes e inventario</small>
          </div>
          <button v-if="messages.length" type="button" class="btn-icon" title="Nueva conversación" @click="clearChat">
            <Icon name="refresh" :size="16" />
          </button>
          <button type="button" class="btn-icon" title="Cerrar" @click="open = false">
            <Icon name="close" :size="16" />
          </button>
        </header>

        <div ref="listEl" class="assistant-messages">
          <div v-if="!messages.length" class="assistant-empty">
            <p>Pregúntame lo que quieras sobre Zola: ventas, ganancias, clientes, pedidos o inventario de las cuentas del emprendimiento.</p>
            <button v-for="s in SUGGESTIONS" :key="s" type="button" class="assistant-suggestion" @click="send(s)">
              {{ s }}
            </button>
          </div>
          <template v-for="(m, i) in messages" :key="i">
            <div v-if="m.role === 'user'" class="msg msg-user">{{ m.text }}</div>
            <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown escapa todo el HTML -->
            <div v-else class="msg msg-assistant" v-html="renderMarkdown(m.text)"></div>
          </template>
          <div v-if="sending" class="msg msg-assistant msg-typing" aria-label="Escribiendo">
            <i></i><i></i><i></i>
          </div>
        </div>

        <p v-if="error" class="assistant-error">{{ error }}</p>

        <form class="assistant-input" @submit.prevent="send()">
          <textarea
            ref="inputEl"
            v-model="draft"
            rows="1"
            maxlength="4000"
            placeholder="Escribe tu pregunta…"
            @keydown="onKeydown"
          ></textarea>
          <button type="submit" class="btn btn-primary" :disabled="sending || !draft.trim()" title="Enviar">
            <Icon name="chevronRight" :size="18" />
          </button>
        </form>
      </section>
    </Transition>

    <button
      type="button"
      class="assistant-bubble"
      :class="{ active: open }"
      :aria-label="open ? 'Cerrar asistente' : 'Abrir asistente IA'"
      @click="toggle"
    >
      <Icon :name="open ? 'close' : 'sparkle'" :size="24" />
    </button>
  </template>
</template>

<style scoped>
.assistant-bubble {
  position: fixed;
  z-index: 95; /* sobre la barra móvil (90), bajo las ventanas (100) */
  right: 24px;
  bottom: 24px;
  width: 56px;
  height: 56px;
  border: none;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  box-shadow: var(--shadow-lg);
  cursor: pointer;
  transition: transform 0.3s var(--ease-spring, ease);
}
.assistant-bubble:hover {
  transform: scale(1.07);
}
.assistant-bubble.active {
  transform: rotate(90deg);
}

.assistant-panel {
  position: fixed;
  z-index: 96;
  right: 24px;
  bottom: 92px;
  width: min(400px, calc(100vw - 32px));
  height: min(600px, calc(100vh - 130px));
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.assistant-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 12px 12px 16px;
  border-bottom: 1px solid var(--border);
}
.assistant-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  flex-shrink: 0;
}
.assistant-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.assistant-title small {
  color: var(--text-muted);
  font-size: 12px;
}

.assistant-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--surface-alt);
}

.assistant-empty p {
  margin: 0 0 12px;
  color: var(--text-muted);
  font-size: 14px;
}
.assistant-suggestion {
  display: block;
  width: 100%;
  text-align: left;
  margin-bottom: 8px;
  padding: 10px 12px;
  font: inherit;
  font-size: 13px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
}
.assistant-suggestion:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.msg {
  max-width: 88%;
  padding: 10px 13px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.msg-user {
  align-self: flex-end;
  white-space: pre-wrap;
  color: #fff;
  background: var(--primary);
  border-bottom-right-radius: 4px;
}
.msg-assistant {
  align-self: flex-start;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}
.msg-assistant :deep(p) {
  margin: 0 0 6px;
}
.msg-assistant :deep(p:last-child) {
  margin-bottom: 0;
}
.msg-assistant :deep(ul),
.msg-assistant :deep(ol) {
  margin: 4px 0 6px;
  padding-left: 20px;
}
.msg-assistant :deep(code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--surface-alt);
  font-size: 13px;
}
.msg-assistant :deep(.md-table) {
  overflow-x: auto;
  margin: 4px 0 6px;
}
.msg-assistant :deep(table) {
  border-collapse: collapse;
  font-size: 13px;
}
.msg-assistant :deep(th),
.msg-assistant :deep(td) {
  padding: 4px 8px;
  border: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}
.msg-assistant :deep(th) {
  background: var(--surface-alt);
}

.msg-typing {
  display: flex;
  gap: 4px;
  padding: 14px 16px;
}
.msg-typing i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-faint);
  animation: typing 1.2s infinite ease-in-out;
}
.msg-typing i:nth-child(2) {
  animation-delay: 0.15s;
}
.msg-typing i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.assistant-error {
  margin: 0;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-soft);
}

.assistant-input {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
}
.assistant-input textarea {
  flex: 1;
  resize: none;
  max-height: 120px;
  field-sizing: content;
  padding: 9px 12px;
  font: inherit;
  font-size: 14px;
  color: var(--text);
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.assistant-input textarea:focus {
  outline: none;
  border-color: var(--primary);
}
.assistant-input .btn {
  padding: 9px 12px;
}

.assistant-panel-enter-active,
.assistant-panel-leave-active {
  transition: opacity 0.2s, transform 0.25s var(--ease-spring, ease);
  transform-origin: bottom right;
}
.assistant-panel-enter-from,
.assistant-panel-leave-to {
  opacity: 0;
  transform: scale(0.92) translateY(10px);
}

/* En el celular la burbuja queda sobre la barra de pestañas y el panel ocupa el ancho. */
@media (max-width: 640px) {
  .assistant-bubble {
    right: 16px;
    bottom: calc(90px + env(safe-area-inset-bottom));
    width: 50px;
    height: 50px;
  }
  .assistant-panel {
    right: 12px;
    left: 12px;
    width: auto;
    top: 12px;
    bottom: calc(150px + env(safe-area-inset-bottom));
    height: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .assistant-bubble,
  .assistant-panel-enter-active,
  .assistant-panel-leave-active {
    transition: none;
  }
}
</style>
