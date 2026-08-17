import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function ScopePlaceholder({
  title,
  description,
  ownerPlan,
}: {
  title: string;
  description: string;
  ownerPlan: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="outline">Interface ready</Badge>
        <span className="text-muted-foreground">Live data boundary: {ownerPlan}</span>
      </CardContent>
    </Card>
  );
}
