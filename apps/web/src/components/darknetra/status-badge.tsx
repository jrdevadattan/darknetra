import { Badge } from '@/components/ui/badge';

export type InvestigatorStatus =
  | 'candidate'
  | 'lead'
  | 'pending-review'
  | 'analyst-confirmed'
  | 'rejected'
  | 'verified'
  | 'warning'
  | 'failed'
  | 'offline';

const STATUS_COPY: Record<InvestigatorStatus, string> = {
  candidate: 'Candidate',
  lead: 'Lead',
  'pending-review': 'Pending analyst review',
  'analyst-confirmed': 'Analyst-confirmed',
  rejected: 'Rejected',
  verified: 'Verified',
  warning: 'Warning',
  failed: 'Failed',
  offline: 'Offline',
};

export function StatusBadge({ status }: { status: InvestigatorStatus }) {
  const destructive = status === 'failed' || status === 'rejected';
  const outline = status === 'candidate' || status === 'pending-review' || status === 'offline';
  return (
    <Badge variant={destructive ? 'destructive' : outline ? 'outline' : 'secondary'}>
      {STATUS_COPY[status]}
    </Badge>
  );
}
