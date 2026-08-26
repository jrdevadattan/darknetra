"use client";

import type { FormEvent } from "react";
import { useId, useState } from "react";
import { ExternalLinkIcon } from "lucide-react";

import { AsyncState } from "@/components/darknetra/async-state";
import { PageHeader } from "@/components/darknetra/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";

import { useIntelligenceIntegrations, useNormalizeIntelligenceIntegration } from "./queries";

const flowSteps = [
  ["1", "Approve source", "An administrator records the authority and collection boundary."],
  ["2", "Collect or import", "A bounded adapter receives a report, link tree, or approved observation."],
  ["3", "Preserve and hash", "The original package is retained with SHA-256 and provenance metadata."],
  ["4", "Extract signals", "Aliases, wallets, links, phrases, and timestamps enter structured review."],
  ["5", "Correlate and decide", "The case graph exposes candidate links for an investigator decision."],
] as const;

export function SourceRegistryLiveView() {
  const integrationsQuery = useIntelligenceIntegrations();
  const normalizeIntegration = useNormalizeIntelligenceIntegration();
  const [adapter, setAdapter] = useState("robin");
  const [sourceName, setSourceName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const id = useId();

  if (integrationsQuery.isPending) {
    return <AsyncState state="loading" title="Loading intelligence integrations" />;
  }

  if (integrationsQuery.isError) {
    const offline = integrationsQuery.error instanceof ApiError && integrationsQuery.error.status === 0;
    return (
      <AsyncState
        state={offline ? "offline" : "error"}
        title={offline ? "Integration service offline" : "Integration catalog unavailable"}
        description="DARKNETRA could not load the authorized intelligence adapter catalog from the API."
      />
    );
  }

  const imports = integrationsQuery.data.items.filter((item) => item.integration_mode === "IMPORT").length;
  const discovery = integrationsQuery.data.items.filter((item) => item.integration_mode === "DISCOVERY").length;
  const importAdapters = integrationsQuery.data.items.filter((item) => item.integration_mode === "IMPORT");

  async function handleNormalize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    await normalizeIntegration.mutateAsync({ adapter, sourceName: sourceName.trim(), file });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Intelligence"
        title="Source Registry"
        description="Controlled OSINT integrations, evidence normalization, and collection-policy boundaries."
      />

      <section className="grid gap-4 md:grid-cols-3" aria-label="Integration metrics">
        {[
          [String(integrationsQuery.data.items.length), "registered integrations", "API-published adapter definitions"],
          [String(imports), "evidence import adapters", "structured outputs accepted for normalization"],
          [String(discovery), "discovery references", "candidate sources require administrator approval"],
        ].map(([value, label, detail]) => (
          <Card key={label}>
            <CardHeader>
              <CardDescription>{label}</CardDescription>
              <CardTitle className="text-3xl">{value}</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground text-sm">{detail}</CardContent>
          </Card>
        ))}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Integration catalog</CardTitle>
          <CardDescription>
            Each project has one explicit role. Repository code is isolated from case data and never auto-installed.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-2">
          {integrationsQuery.data.items.map((integration) => (
            <article key={integration.slug} className="rounded-xl border p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <a
                    className="inline-flex items-center gap-2 font-semibold hover:underline"
                    href={integration.repository_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {integration.name}
                    <ExternalLinkIcon className="size-4" aria-hidden="true" />
                  </a>
                  <p className="mt-2 text-muted-foreground text-sm">{integration.pipeline_role}</p>
                </div>
                <Badge variant="secondary">{integration.integration_mode}</Badge>
              </div>
              {integration.accepted_outputs.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {integration.accepted_outputs.map((output) => (
                    <Badge key={output} variant="outline">
                      {output}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Normalize intelligence package</CardTitle>
          <CardDescription>
            Process a Robin report or TorBot JSON tree into a hashed observation package before case ingestion.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 lg:grid-cols-[1fr_1fr_1.2fr_auto] lg:items-end" onSubmit={handleNormalize}>
            <FieldGroup className="contents">
              <Field>
                <FieldLabel htmlFor={`${id}-adapter`}>Adapter</FieldLabel>
                <select
                  id={`${id}-adapter`}
                  className="h-9 rounded-md border bg-background px-3 text-sm"
                  value={adapter}
                  onChange={(event) => setAdapter(event.target.value)}
                >
                  {importAdapters.map((item) => (
                    <option key={item.slug} value={item.slug}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-source-name`}>Source name</FieldLabel>
                <Input
                  id={`${id}-source-name`}
                  minLength={3}
                  maxLength={200}
                  required
                  value={sourceName}
                  onChange={(event) => setSourceName(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-package`}>Intelligence package</FieldLabel>
                <Input
                  id={`${id}-package`}
                  type="file"
                  accept={adapter === "torbot" ? "application/json,.json" : "text/markdown,text/plain,.md,.txt"}
                  required
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </Field>
              <Button type="submit" disabled={normalizeIntegration.isPending || !file}>
                {normalizeIntegration.isPending ? "Normalizing..." : "Normalize package"}
              </Button>
            </FieldGroup>
          </form>
          {normalizeIntegration.isError ? (
            <FieldError className="mt-4">{normalizeIntegration.error.message}</FieldError>
          ) : null}
          {normalizeIntegration.data ? (
            <div className="mt-4 rounded-xl border p-4" role="status">
              <p className="font-semibold">Package normalized</p>
              <p className="mt-1 text-muted-foreground text-sm">
                SHA-256 {normalizeIntegration.data.content_sha256.slice(0, 12)}… · {normalizeIntegration.data.observations.length}{" "}
                observation{normalizeIntegration.data.observations.length === 1 ? "" : "s"}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Authorized intelligence flow</CardTitle>
          <CardDescription>How an approved observation becomes reviewable case intelligence.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-3 lg:grid-cols-5">
            {flowSteps.map(([number, title, detail]) => (
              <li key={number} className="rounded-xl border p-4">
                <Badge variant="outline">Step {number}</Badge>
                <p className="mt-3 font-semibold">{title}</p>
                <p className="mt-2 text-muted-foreground text-sm">{detail}</p>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Collector policy boundary</CardTitle>
          <CardDescription>Enforced before any future network request leaves the isolated collector.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {["GET and HEAD only", "Depth 1 / 25 pages", "No credentials or cookies", "Executable downloads blocked"].map(
            (control) => (
              <div key={control} className="rounded-lg border p-3 font-medium text-sm">
                {control}
              </div>
            ),
          )}
        </CardContent>
      </Card>
    </div>
  );
}
