import { WorkspaceShell } from "@/components/workspace-shell";

export default async function CasePage({ params }: { params: Promise<{ caseId: string }> }) { const { caseId } = await params; return <WorkspaceShell initialCaseId={caseId} />; }
