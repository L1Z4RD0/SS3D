import client from "./client";

export const getMonthlyHistory = () => client.get("/api/history/monthly").then((r) => r.data);
