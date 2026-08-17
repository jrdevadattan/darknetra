import { ScopePlaceholder } from './scope-placeholder';

export function CaseScopePage({
  title,
  description,
  ownerPlan,
}: {
  title: string;
  description: string;
  ownerPlan: string;
}) {
  return <ScopePlaceholder title={title} description={description} ownerPlan={ownerPlan} />;
}
