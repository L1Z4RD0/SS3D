import client from "./client";

export const computeQuote = (payload) =>
  client.post("/api/calculator/quote", payload).then((r) => r.data);

export const saveQuoteAsSale = (payload) =>
  client.post("/api/calculator/quote/save-as-sale", payload).then((r) => r.data);
