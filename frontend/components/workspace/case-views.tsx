"use client";

import type { S, CaseView } from "@/lib/types";
import {
  AlertsView,
  MonitoringView,
  ReportsView,
} from "./case-operations-views";
import { AuditView, MembersView } from "./case-admin-views";
import { FindingsView, RelationshipsView } from "./case-analysis-views";
import {
  EntitiesView,
  EvidenceView,
  OverviewView,
  SearchView,
} from "./case-data-views";

export function CaseViews({
  caseData,
  user,
  view,
  onEvidence,
}: {
  caseData: S<"Case">;
  user: S<"UserMe">;
  view: CaseView;
  onEvidence: (id: string) => void;
}) {
  const props = { caseData, user, onEvidence };
  switch (view) {
    case "overview":
      return <OverviewView {...props} />;
    case "evidence":
      return <EvidenceView {...props} />;
    case "search":
      return <SearchView {...props} />;
    case "entities":
      return <EntitiesView {...props} />;
    case "relationships":
      return <RelationshipsView {...props} />;
    case "findings":
      return <FindingsView {...props} />;
    case "monitoring":
      return <MonitoringView {...props} />;
    case "alerts":
      return <AlertsView {...props} />;
    case "reports":
      return <ReportsView {...props} />;
    case "members":
      return <MembersView {...props} />;
    case "audit":
      return <AuditView {...props} />;
  }
}
