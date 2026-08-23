import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function MetricLinkCard({
  label,
  value,
  description,
  href,
}: {
  label: string;
  value: string | number;
  description: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`${label}: ${value}. ${description}`}
    >
      <Card className="h-full transition-colors group-hover:bg-muted/30">
        <CardHeader>
          <CardDescription>{label}</CardDescription>
          <CardTitle className="flex items-center justify-between text-2xl">
            <span>{value}</span>
            <ArrowUpRight className="size-4 text-muted-foreground" aria-hidden="true" />
          </CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-xs">{description}</CardContent>
      </Card>
    </Link>
  );
}
