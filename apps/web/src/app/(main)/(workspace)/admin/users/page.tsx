import { PageHeader } from '@/components/darknetra/page-header';
import { UserTable } from '@/features/admin/users/user-table';

export default function UsersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Users"
        description="Read-only investigator directory exposing only identity, active state, and global roles."
      />
      <UserTable />
    </div>
  );
}
