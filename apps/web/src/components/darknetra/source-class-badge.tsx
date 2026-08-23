import { Badge } from '@/components/ui/badge';

export type SourceClass = 'SYNTHETIC' | 'RESEARCH_ARCHIVE';

export function SourceClassBadge({ sourceClass }: { sourceClass: SourceClass }) {
  return (
    <Badge variant="outline" title="Source class">
      {sourceClass}
    </Badge>
  );
}
