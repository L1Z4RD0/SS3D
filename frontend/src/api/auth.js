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

export function refresh() {
  return client.post("/api/auth/refresh").then((r) => r.data);
}
