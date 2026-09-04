import client from "./client";

export const listUsers = () => client.get("/api/admin/users").then((r) => r.data);

export const createUser = (payload) => client.post("/api/admin/users", payload).then((r) => r.data);

export const deactivateUser = (id) =>
  client.patch(`/api/admin/users/${id}/deactivate`).then((r) => r.data);

export const reactivateUser = (id) =>
  client.patch(`/api/admin/users/${id}/reactivate`).then((r) => r.data);

export const listAuditLogs = (params = {}) =>
  client.get("/api/admin/audit-logs", { params }).then((r) => r.data);
