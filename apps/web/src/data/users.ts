export const users = [
  {
    id: 'demo-admin',
    name: 'Demo Administrator',
    username: 'demo-admin',
    email: 'admin@darknetra.local',
    avatar: '',
    role: 'ADMIN',
  },
  {
    id: 'demo-analyst',
    name: 'Demo Analyst',
    username: 'demo-analyst',
    email: 'analyst@darknetra.local',
    avatar: '',
    role: 'ANALYST',
  },
] as const;

export const rootUser = users[0];
