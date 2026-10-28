import client from "./client";

// Asistente IA de consultas (solo las cuentas del emprendimiento).
export const getAssistantAccess = () => client.get("/api/assistant/access").then((r) => r.data);
export const sendAssistantChat = (messages) =>
  client.post("/api/assistant/chat", { messages }).then((r) => r.data.reply);
