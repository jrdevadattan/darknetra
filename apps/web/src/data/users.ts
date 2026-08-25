export const users = [
  {
    id: "darknetra-admin",
    name: "DARKNETRA Administrator",
    username: "administrator",
    email: "admin@darknetra.local",
    avatar: "",
    role: "ADMIN",
  },
  {
    id: "darknetra-analyst",
    name: "DARKNETRA Analyst",
    username: "analyst",
    email: "analyst@darknetra.local",
    avatar: "",
    role: "ANALYST",
  },
] as const;

export const rootUser = users[0];
