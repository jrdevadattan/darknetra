import { AsyncState } from "@/components/darknetra/async-state";
import { PageHeader } from "@/components/darknetra/page-header";
import { StatusBadge } from "@/components/darknetra/status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { HealthApiError, fetchHealth } from "@/lib/api/health";

export const dynamic = "force-dynamic";

export default async function SystemHealthPage() {
  try {
    const health = await fetchHealth();
    const api = health.components.find((component) => component.name === "api");

    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Operations"
          title="System Health"
          description="Measured service readiness. A successful page render alone is never treated as API health."
        />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-3">
              <span>DARKNETRA API</span>
              <StatusBadge status={api?.status === "ready" ? "verified" : "warning"} />
            </CardTitle>
            <CardDescription>Live probe: /api/v1/health/ready</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">Reported status:</span> {health.status}
            </div>
            <div>
              <span className="text-muted-foreground">Build version:</span> {health.version}
            </div>
          </CardContent>
        </Card>
        <AsyncState
          state="partial"
          title="Additional components are not active yet"
          description="PostgreSQL, Redis, worker, graph projector, evidence store, models, and optional collector appear only after their implementation plans add measurable probes."
        />
      </div>
    );
  } catch (error) {
    const detail =
      error instanceof HealthApiError
        ? `${error.kind === "http" ? `HTTP ${error.status}: ` : ""}${error.message}`
        : "The DARKNETRA API probe failed.";

    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Operations"
          title="System Health"
          description="Measured service readiness. A successful page render alone is never treated as API health."
        />
        <AsyncState
          state="offline"
          title="DARKNETRA API unreachable"
          description={`${detail} This is reported as unavailable rather than shown as a false green state.`}
        />
      </div>
    );
  }
}
