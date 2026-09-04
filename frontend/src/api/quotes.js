import client from "./client";

export const listQuotes = (params = {}) => client.get("/api/quotes", { params }).then((r) => r.data);

export const getQuote = (id) => client.get(`/api/quotes/${id}`).then((r) => r.data);

export const createQuote = (payload) => client.post("/api/quotes", payload).then((r) => r.data);
