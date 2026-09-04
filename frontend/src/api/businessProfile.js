import client from "./client";

export const getBusinessProfile = () => client.get("/api/business-profile").then((r) => r.data);

export const updateBusinessProfile = (payload) =>
  client.put("/api/business-profile", payload).then((r) => r.data);
