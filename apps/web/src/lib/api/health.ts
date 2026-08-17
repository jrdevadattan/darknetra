export interface ReadyHealthComponent {
  name: "api";
  status: "ready";
}

export interface ReadyHealthResponse {
  status: "ready";
  version: string;
  components: ReadyHealthComponent[];
}

export type HealthApiErrorKind = "http" | "network" | "contract";

export class HealthApiError extends Error {
  readonly kind: HealthApiErrorKind;
  readonly status?: number;

  constructor(kind: HealthApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = "HealthApiError";
    this.kind = kind;
    this.status = status;
  }
}

function apiBaseUrl(): string {
  return (
    process.env.DARKNETRA_API_BASE_URL ??
    process.env.NEXT_PUBLIC_DARKNETRA_API_BASE_URL ??
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

function isReadyHealth(value: unknown): value is ReadyHealthResponse {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ReadyHealthResponse>;
  return (
    candidate.status === "ready" &&
    typeof candidate.version === "string" &&
    candidate.version.length > 0 &&
    Array.isArray(candidate.components) &&
    candidate.components.every(
      (component) => component?.name === "api" && component?.status === "ready",
    )
  );
}

export async function fetchHealth(): Promise<ReadyHealthResponse> {
  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      throw new HealthApiError(
        "http",
        `DARKNETRA API returned HTTP ${response.status}.`,
        response.status,
      );
    }

    const payload: unknown = await response.json();
    if (!isReadyHealth(payload)) {
      throw new HealthApiError("contract", "DARKNETRA API returned an invalid health payload.");
    }
    return payload;
  } catch (error) {
    if (error instanceof HealthApiError) throw error;
    throw new HealthApiError(
      "network",
      error instanceof Error ? error.message : "DARKNETRA API is unreachable.",
    );
  }
}
