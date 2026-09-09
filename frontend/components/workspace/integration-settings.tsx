"use client";
import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  CircleAlert,
  KeyRound,
  Landmark,
  LoaderCircle,
  RadioTower,
  RefreshCw,
  ShieldCheck,
  CloudDownload,
} from "lucide-react";
import type { ProviderIntegration } from "@/lib/provider-integrations";

export function IntegrationSettings() {
  const [providers, setProviders] = useState<ProviderIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch("/api/integrations", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then((data) => setProviders(data.providers))
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Could not read integration status. Try again.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [revision]);
  return (
    <section
      className="integration-settings"
      aria-label="Intelligence integrations"
    >
      <div className="integration-heading">
        <h3>Intelligence tools</h3>
        <button
          type="button"
          className="icon-button"
          aria-label="Refresh integration status"
          title="Refresh integration status"
          disabled={loading}
          onClick={() => setRevision(revision + 1)}
        >
          {loading ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <RefreshCw size={15} />
          )}
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {providers.map((provider) => {
        const Icon =
          provider.id === "chainalysis"
            ? Landmark
            : provider.id === "flashpoint"
              ? RadioTower
              : provider.id === "apify"
                ? CloudDownload
                : ShieldCheck;
        return (
          <article className="integration-card" key={provider.id}>
            <span className="integration-icon">
              <Icon size={19} />
            </span>
            <div>
              <strong>{provider.name}</strong>
              <p>{provider.capability}</p>
              <span className={`integration-state ${provider.state}`}>
                {provider.state === "configured_unverified" ? (
                  <ShieldCheck size={12} />
                ) : provider.state === "configuration_error" ? (
                  <CircleAlert size={12} />
                ) : (
                  <KeyRound size={12} />
                )}
                {provider.state === "configured_unverified"
                  ? "Configured · verify access before use"
                  : provider.state === "configuration_error"
                    ? "Check configuration"
                    : "API key required"}
              </span>
              {provider.message && <p>{provider.message}</p>}
            </div>
            <a
              className="icon-button"
              aria-label={`Open ${provider.name} setup`}
              title={`Open ${provider.name} setup`}
              href={provider.setupUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ArrowUpRight size={16} />
            </a>
          </article>
        );
      })}
      <details className="integration-setup">
        <summary>
          <KeyRound size={14} />
          Connect your accounts
        </summary>
        <p>
          On the computer running this app, copy{" "}
          <code>frontend/providers.example.json</code> to{" "}
          <code>frontend/.codex-chat/providers.json</code> and add your API keys
          there. Then refresh this status. Keys stay out of chat and browser
          storage.
        </p>
        <p>
          Available access depends on your account. Reactor tracing and KYT
          monitoring require their separate customer integrations.
        </p>
      </details>
    </section>
  );
}
