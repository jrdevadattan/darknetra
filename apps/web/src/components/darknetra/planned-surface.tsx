import { PageHeader } from './page-header';
import { ScopePlaceholder } from './scope-placeholder';

export function PlannedSurface({
  eyebrow,
  title,
  description,
  ownerPlan,
}: {
  eyebrow: string;
  title: string;
  description: string;
  ownerPlan: string;
}) {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
      <ScopePlaceholder title={`${title} interface`} description="No live or fabricated records are shown in this Plan 01 shell." ownerPlan={ownerPlan} />
    </div>
  );
}
