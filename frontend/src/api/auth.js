import client from "./client";

export function login(username, password) {
  return client.post("/api/auth/login", { username, password }).then((r) => r.data);
}

export function logout() {
  return client.post("/api/auth/logout");
}

export function fetchMe() {
  return client.get("/api/auth/me").then((r) => r.data);
}

export function fetchObservedUsers() {
  return client.get("/api/auth/me/observed-users").then((r) => r.data);
}

export function refresh() {
  return client.post("/api/auth/refresh").then((r) => r.data);
}

// Marca la ventana de Novedades como vista por este usuario (se guarda en su cuenta).
export function markReleaseSeen(release) {
  return client.post("/api/auth/me/release-seen", { release });
}
