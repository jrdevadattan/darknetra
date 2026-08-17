import { AsyncState } from '@/components/darknetra/async-state';
import { PageHeader } from '@/components/darknetra/page-header';
import { RoleMatrix } from '@/features/admin/roles/role-matrix';

export default function RolesPage() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" title="Roles & Permissions" description="Read-only Plan 01 matrix. Real enforcement is server-side and case-scoped in Plan 02." />
      <AsyncState state="partial" title="Read-only contract" description="There is intentionally no Save action until authenticated RBAC APIs exist." />
      <RoleMatrix />
    </div>
  );
}
