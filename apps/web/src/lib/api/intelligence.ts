import { apiFetch } from "@/lib/api/client";

export type IntegrationMode = "IMPORT" | "REFERENCE" | "DISCOVERY";

export interface ApiIntelligenceIntegration {
  slug: string;
  name: string;
  repository_url: string;
  integration_mode: IntegrationMode;
  pipeline_role: string;
  accepted_outputs: string[];
}

export interface ApiIntelligenceIntegrationList {
  items: ApiIntelligenceIntegration[];
}

export interface ApiNormalizedObservation {
  kind: string;
  value: string;
  provenance: string;
  title: string | null;
  parent: string | null;
}

export interface ApiIntegrationNormalizeResult {
  adapter: string;
  content_sha256: string;
  observations: ApiNormalizedObservation[];
}

export interface NormalizeIntegrationInput {
  adapter: string;
  sourceName: string;
  file: File;
}

export function listIntelligenceIntegrations(): Promise<ApiIntelligenceIntegrationList> {
  return apiFetch<ApiIntelligenceIntegrationList>("/api/v1/intelligence/integrations");
}

export async function normalizeIntelligenceIntegration(
  input: NormalizeIntegrationInput,
): Promise<ApiIntegrationNormalizeResult> {
  const payloadBase64 = await readFileBase64(input.file);
  return apiFetch<ApiIntegrationNormalizeResult>(
    `/api/v1/intelligence/integrations/${encodeURIComponent(input.adapter)}/normalize`,
    {
      method: "POST",
      body: JSON.stringify({ source_name: input.sourceName, payload_base64: payloadBase64 }),
    },
  );
}

function readFileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Could not read intelligence package."));
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Could not encode intelligence package."));
        return;
      }
      resolve(reader.result.slice(reader.result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}
