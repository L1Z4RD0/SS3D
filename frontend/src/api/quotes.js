import client from "./client";

export const createQuote = (payload) => client.post("/api/quotes", payload).then((r) => r.data);
