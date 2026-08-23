export type ApiErrorCode =
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "VALIDATION_ERROR"
  | "SERVER_ERROR"
  | "HTTP_ERROR"
  | "NETWORK_ERROR"
  | "REQUEST_ABORTED";

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | string;
  readonly details: unknown;

  constructor(options: {
    status: number;
    code: ApiErrorCode | string;
    message: string;
    details?: unknown;
    cause?: unknown;
  }) {
    super(options.message, { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
  }
}

export function defaultApiErrorCode(status: number): ApiErrorCode {
  if (status === 401) return "UNAUTHORIZED";
  if (status === 403) return "FORBIDDEN";
  if (status === 404) return "NOT_FOUND";
  if (status === 422) return "VALIDATION_ERROR";
  if (status >= 500) return "SERVER_ERROR";
  return "HTTP_ERROR";
}
