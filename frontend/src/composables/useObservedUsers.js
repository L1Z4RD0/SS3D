import { ref, computed } from "vue";
import * as authApi from "../api/auth";
import { useAuthStore } from "../stores/auth";

/* Usuarios que el observador (watcher) tiene asignados. Un watcher recibe impresoras,
   filamentos e insumos de todos ellos juntos, y cada uno trae su `owner_id`; esto
   permite mostrar de quién es cada cosa. Para cualquier otro rol queda vacío y
   `ownerName` devuelve "" (todo es propio, no hace falta aclararlo). */
export function useObservedUsers() {
  const auth = useAuthStore();
  const observedUsers = ref([]);
  const loadingObserved = ref(false);

  const namesById = computed(() => Object.fromEntries(observedUsers.value.map((u) => [u.id, u.username])));

  async function loadObservedUsers() {
    if (!auth.isWatcher) return;
    loadingObserved.value = true;
    try {
      observedUsers.value = await authApi.fetchObservedUsers();
    } finally {
      loadingObserved.value = false;
    }
  }

  function ownerName(ownerId) {
    if (!auth.isWatcher || !ownerId) return "";
    return namesById.value[ownerId] || (loadingObserved.value ? "…" : "usuario desconocido");
  }

  return { observedUsers, loadingObserved, namesById, loadObservedUsers, ownerName };
}
