import client from "./client";

export const getFilamentCatalog = () => client.get("/api/catalog/filaments").then((r) => r.data);
