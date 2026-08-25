import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

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
        <Badge variant="outline">Workspace ready</Badge>
        <Badge variant="secondary">Access scoped</Badge>
        <span className="text-muted-foreground">Processing area: {ownerPlan}</span>
      </CardContent>
    </Card>
  );
}
