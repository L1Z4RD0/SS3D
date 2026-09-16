import { ref } from "vue";
import * as catalogApi from "../api/catalog";

// Module-level singleton (same pattern as useTheme.js/useMobileNav.js): the brand/
// material/color catalog is global and effectively static for the session (it only
// changes via an admin/migration seed, never through normal app usage -- "otra marca/
// color..." in Inventario is just free text on a filament, not a write to this catalog).
// Shared here so opening the filament picker repeatedly, or visiting Inventario, doesn't
// each fire their own independent GET /api/catalog/filaments.
const catalog = ref({ brands: [], materials: [], colors: [] });
let loaded = false;
let loadPromise = null;

export function useFilamentCatalog() {
  function ensureFilamentCatalog() {
    if (loaded) return Promise.resolve(catalog.value);
    if (!loadPromise) {
      loadPromise = catalogApi
        .getFilamentCatalog()
        .then((data) => {
          catalog.value = data;
          loaded = true;
          return catalog.value;
        })
        .finally(() => {
          loadPromise = null;
        });
    }
    return loadPromise;
  }

  return { catalog, ensureFilamentCatalog };
}
