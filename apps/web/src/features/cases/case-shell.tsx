"use client";

import type { ReactNode } from "react";

import { AsyncState } from "@/components/darknetra/async-state";
import { CaseTabs } from "@/components/darknetra/case-tabs";
import { PageHeader } from "@/components/darknetra/page-header";
import { SourceClassBadge } from "@/components/darknetra/source-class-badge";
import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/api/errors";

import { useCase } from "./queries";

export function CaseShell({ caseId, children }: { caseId: string; children: ReactNode }) {
  const caseQuery = useCase(caseId);

  if (caseQuery.isPending) {
    return <AsyncState state="loading" />;
  }

  if (caseQuery.isError) {
    if (caseQuery.error instanceof ApiError && caseQuery.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="Case service offline"
          description="The case API could not be reached. Substitute case records are not displayed."
        />
      );
    }

    if (caseQuery.error instanceof ApiError && (caseQuery.error.status === 403 || caseQuery.error.status === 404)) {
      return (
        <AsyncState
          state="error"
          title="Case unavailable"
          description="The requested case is unavailable to this session."
        />
      );
    }

    return (
      <AsyncState state="error" title="Unable to load case" description="The case could not be loaded from the API." />
    );
  }

  const currentCase = caseQuery.data;

  return (
    <div className="space-y-5">
      {caseQuery.isFetching ? (
        <AsyncState
          state="stale"
          title="Refreshing case"
          description="Showing the last successful case response while a fresh response is requested."
        />
      ) : null}
      <PageHeader
        eyebrow={currentCase.caseCode}
        title={currentCase.title}
        description={`Owner: ${currentCase.owner} · Sensitivity: ${currentCase.sensitivity} · Stage: ${currentCase.processStage}`}
        actions={
          <>
            <Badge variant="secondary">{currentCase.status}</Badge>
            <SourceClassBadge sourceClass={currentCase.sourceClass} />
          </>
        }
      />
      <CaseTabs caseId={currentCase.id} />
      {children}
    </div>
  );
}
