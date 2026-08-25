import { PageHeader } from "./page-header";
import { ScopePlaceholder } from "./scope-placeholder";

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
      <ScopePlaceholder
        title={`${title} workspace`}
        description="Operational controls, metadata, and review states are shown only inside the authenticated workspace."
        ownerPlan={ownerPlan}
      />
    </div>
  );
}
