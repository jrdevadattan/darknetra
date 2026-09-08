"use client";

import { useState } from "react";
import {
  Download,
  FileCheck2,
  FileText,
  Hash,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { download, useApi } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { S } from "@/lib/types";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Loading,
  Modal,
  StatusBadge,
  date,
} from "./shared";
import { FormFeedback, humanize, useCaseAction } from "./case-forms";

export function EvidenceDetail({
  caseId,
  evidenceId,
  user,
  caseData,
  onClose,
}: {
  caseId: string;
  evidenceId: string;
  user: S<"UserMe">;
  caseData: S<"Case">;
  onClose: () => void;
}) {
  const detail = useApi<S<"Evidence">>(
    `/cases/${caseId}/evidence/${evidenceId}`,
    (data) => (data?.status === "PROCESSING" ? 2000 : false),
  );
  const evidence = detail.data;
  const textAvailable =
    evidence?.derivatives?.some(
      (item) => item.kind === "TEXT" && item.status === "READY",
    ) ?? false;
  const text = useApi<S<"TextDerivative">>(
    textAvailable
      ? `/cases/${caseId}/evidence/${evidenceId}/derivatives/TEXT`
      : null,
  );
  const contextEnd = Math.min(text.data?.text.length ?? 0, 600);
  const context = useApi<S<"Context">>(
    contextEnd > 0
      ? `/cases/${caseId}/evidence/${evidenceId}/context?start=0&end=${contextEnd}&pad=200`
      : null,
  );
  const verify = useCaseAction(caseId);
  const [downloadError, setDownloadError] = useState<unknown>(null);
  const [downloading, setDownloading] = useState(false);
  const canViewOriginal = can(user, caseData, "write");
  const unredactedReport =
    evidence?.source_class === "REPORT" && evidence.meta?.redacted === false;
  const canDownloadOriginal =
    canViewOriginal && (!unredactedReport || can(user, caseData, "export"));

  async function getOriginal() {
    if (!evidence) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await download(
        `/cases/${caseId}/evidence/${evidence.id}/original`,
        evidence.original_filename,
      );
    } catch (caught) {
      setDownloadError(caught);
    } finally {
      setDownloading(false);
    }
  }

  async function verifyHash() {
    const result = await verify.run<S<"VerifyResult">>(
      `/cases/${caseId}/evidence/${evidenceId}/verify`,
      "POST",
      undefined,
      "Integrity check recorded",
    );
    if (result && !result.hash_verified) {
      verify.fail(
        new Error(
          "Hash verification failed. The evidence record has been marked failed and the custody event was recorded.",
        ),
      );
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={
        evidence
          ? `${evidence.code} · ${evidence.original_filename}`
          : "Evidence record"
      }
      description="Immutable metadata, captured text, and chain of custody."
      wide
    >
      {detail.isLoading ? <Loading label="Loading evidence" /> : null}
      <ErrorBanner error={detail.error} retry={() => void detail.refetch()} />
      {evidence ? (
        <div className="content-stack">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={evidence.status} />
            <span className="muted text-sm">
              {humanize(evidence.kind)} · {humanize(evidence.source_class)}
            </span>
          </div>

          <section className="panel-card">
            <h2 className="flex items-center gap-2">
              <Hash size={17} />
              Immutable record
            </h2>
            <dl className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="muted text-xs uppercase tracking-wide">
                  SHA-256
                </dt>
                <dd className="mt-1 break-all font-mono text-xs">
                  {evidence.sha256}
                </dd>
              </div>
              <div>
                <dt className="muted text-xs uppercase tracking-wide">
                  Captured
                </dt>
                <dd className="mt-1 text-sm">{date(evidence.captured_at)}</dd>
              </div>
              <div>
                <dt className="muted text-xs uppercase tracking-wide">
                  MIME / size
                </dt>
                <dd className="mt-1 text-sm">
                  {evidence.mime} · {evidence.size_bytes.toLocaleString()} bytes
                </dd>
              </div>
              <div>
                <dt className="muted text-xs uppercase tracking-wide">
                  Origin
                </dt>
                <dd className="mt-1 text-sm">{humanize(evidence.origin)}</dd>
              </div>
              {evidence.parent ? (
                <div>
                  <dt className="muted text-xs uppercase tracking-wide">
                    Parent evidence
                  </dt>
                  <dd className="mt-1 font-mono text-sm">
                    {evidence.parent.code}
                  </dd>
                </div>
              ) : null}
              {evidence.requested_by ? (
                <div>
                  <dt className="muted text-xs uppercase tracking-wide">
                    Requested by
                  </dt>
                  <dd className="mt-1 text-sm">
                    {humanize(evidence.requested_by.kind)}
                  </dd>
                </div>
              ) : null}
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={verify.busy || !canViewOriginal}
                onClick={() => void verifyHash()}
              >
                <ShieldCheck size={15} />
                Verify hash
              </Button>
              <Button
                variant="outline"
                disabled={downloading || !canDownloadOriginal}
                onClick={() => void getOriginal()}
              >
                <Download size={15} />
                {downloading ? "Preparing…" : "Download original"}
              </Button>
            </div>
            {!canViewOriginal ? (
              <p className="muted mt-3 text-xs">
                Analyst evidence access is required to verify or download the
                original.
              </p>
            ) : unredactedReport && !canDownloadOriginal ? (
              <p className="muted mt-3 text-xs">
                Export permission is required for an unredacted report original.
              </p>
            ) : null}
            <FormFeedback
              busy={verify.busy}
              error={verify.error}
              message={verify.message}
            />
            <ErrorBanner error={downloadError} />
          </section>

          {evidence.warnings?.length ? (
            <section className="panel-card border-amber-500/30">
              <h2 className="flex items-center gap-2 text-amber-300">
                <TriangleAlert size={17} />
                Recorded warnings
              </h2>
              <ul className="mt-3 space-y-2 text-sm">
                {evidence.warnings.map((warning) => (
                  <li key={warning}>{humanize(warning)}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="panel-card">
            <h2 className="flex items-center gap-2">
              <FileText size={17} />
              Captured text
            </h2>
            {text.isLoading ? (
              <Loading label="Loading text derivative" />
            ) : null}
            <ErrorBanner error={text.error} />
            {context.data ? (
              <div className="mt-4">
                <p className="muted mb-2 text-xs">
                  Context from line {context.data.line_no ?? 1}; the original
                  bytes remain unchanged.
                </p>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-black/20 p-4 font-mono text-xs leading-6">
                  {context.data.before}
                  <mark className="bg-amber-300/25 text-inherit">
                    {context.data.text}
                  </mark>
                  {context.data.after}
                </pre>
              </div>
            ) : !textAvailable && !text.isLoading ? (
              <EmptyState
                title="Text is not available"
                description="This item has no ready TEXT derivative. Its metadata and custody record remain available."
                icon={<FileText size={22} />}
              />
            ) : null}
          </section>

          <section className="panel-card">
            <h2 className="flex items-center gap-2">
              <FileCheck2 size={17} />
              Derivatives
            </h2>
            {evidence.derivatives?.length ? (
              <div className="table-wrap mt-3">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Kind</th>
                      <th>Status</th>
                      <th>Extractor</th>
                      <th>Version</th>
                      <th>Text</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.derivatives.map((item) => (
                      <tr key={item.id}>
                        <td>{humanize(item.kind)}</td>
                        <td>
                          <StatusBadge status={item.status} />
                        </td>
                        <td>{item.extractor}</td>
                        <td>v{item.version}</td>
                        <td>
                          {item.text_len == null
                            ? "—"
                            : `${item.text_len.toLocaleString()} chars`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted mt-3 text-sm">
                No derivatives have been recorded.
              </p>
            )}
          </section>

          <section className="panel-card">
            <h2 className="flex items-center gap-2">
              <ShieldCheck size={17} />
              Chain of custody
            </h2>
            {evidence.custody?.length ? (
              <ol className="mt-4 space-y-4 border-l border-border pl-5">
                {evidence.custody.map((item, index) => (
                  <li key={`${item.at}-${index}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="text-sm">
                        {humanize(item.action)}
                      </strong>
                      {item.hash_verified != null ? (
                        <StatusBadge
                          status={item.hash_verified ? "VERIFIED" : "FAILED"}
                        />
                      ) : null}
                    </div>
                    <p className="muted mt-1 text-xs">
                      {date(item.at)} · {item.actor.display}
                    </p>
                    {item.note ? (
                      <p className="mt-2 text-sm">{item.note}</p>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted mt-3 text-sm">No custody events returned.</p>
            )}
          </section>
        </div>
      ) : null}
    </Modal>
  );
}
