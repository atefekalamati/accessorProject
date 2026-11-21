import type { components } from "./schema.gen";

export type ErrorResponse = components["schemas"]["ErrorResponse"];

/** One entry of `error.details`; the contract leaves its shape open. */
export type ErrorDetail = Record<string, unknown> & { type?: string; field?: string };

/**
 * An API error. UI logic relies only on `code` and `details[].type` (FRONTEND.md §1);
 * `message` is for developers and is never shown. `requestId` is shown in error notices.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];
  readonly requestId: string | null;
  /** Seconds from the Retry-After header (429), if any. */
  readonly retryAfter: number | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: ErrorDetail[];
    requestId?: string | null;
    retryAfter?: number | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? [];
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
  }

  hasDetailType(type: string): boolean {
    return this.details.some((detail) => detail.type === type);
  }
}

export function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string"
  );
}

/** Builds an ApiError from any failed response, whatever its body. */
export function toApiError(response: Response, body: unknown): ApiError {
  const retryHeader = response.headers.get("retry-after");
  const retryAfter = retryHeader !== null && /^\d+$/.test(retryHeader) ? Number(retryHeader) : null;
  const headerRequestId = response.headers.get("x-request-id");
  if (isErrorResponse(body)) {
    return new ApiError({
      status: response.status,
      code: body.error.code,
      message: body.error.message,
      details: Array.isArray(body.error.details) ? (body.error.details as ErrorDetail[]) : [],
      requestId: body.request_id || headerRequestId,
      retryAfter,
    });
  }
  return new ApiError({
    status: response.status,
    code: response.status >= 500 ? "SERVER_ERROR" : "UNKNOWN_ERROR",
    message: `HTTP ${response.status}`,
    requestId: headerRequestId,
    retryAfter,
  });
}

/**
 * Unwraps an openapi-fetch result: the data, or a thrown ApiError. For react-query.
 * Responses without a body (204) give `undefined`.
 */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok || error !== undefined) throw toApiError(response, error);
  return data as T;
}
