import client from "./client";

export const getSettings = () => client.get("/api/calculator/settings").then((r) => r.data);

export const updateSettings = (payload) =>
  client.put("/api/calculator/settings", payload).then((r) => r.data);

export const computeQuote = (payload) =>
  client.post("/api/calculator/quote", payload).then((r) => r.data);

export const saveQuoteAsSale = (payload) =>
  client.post("/api/calculator/quote/save-as-sale", payload).then((r) => r.data);
