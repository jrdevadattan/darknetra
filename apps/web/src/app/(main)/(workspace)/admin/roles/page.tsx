import { PageHeader } from '@/components/darknetra/page-header';
import { RolePermissionMatrix } from '@/features/admin/roles/role-permission-matrix';

export default function RolesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Roles & Permissions"
        description="Read-only permission truth returned by the same backend policy source used for enforcement."
      />
      <RolePermissionMatrix />
    </div>
  );
}
