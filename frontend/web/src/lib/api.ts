import type {
  ActionResult,
  AuditReport,
  CloseView,
  Decision,
  LearningView,
  ObligationDetail,
  VendorsView,
} from "./api-types";

/** Where the backend listens. Override with NEXT_PUBLIC_API_URL. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** The backend did not answer, as opposed to answering with an error. */
export class BackendUnreachableError extends Error {
  constructor(cause?: unknown) {
    super(
      "The TrueUp backend is not reachable. Start it with `uv run python scripts/serve.py` in backend/.",
      { cause },
    );
    this.name = "BackendUnreachableError";
  }
}

/** The backend answered with an error, carrying its `detail` message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch (error) {
    throw new BackendUnreachableError(error);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const getClose = () => request<CloseView>("/api/close");
export const getObligation = (id: string) =>
  request<ObligationDetail>(`/api/obligations/${encodeURIComponent(id)}`);
/** The Auditor's report for one obligation, or null when this build has no Auditor. */
export async function getAudit(id: string): Promise<AuditReport | null> {
  try {
    return await request<AuditReport>(`/api/audit/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError) return null;
    throw error;
  }
}

export const getLearning = () => request<LearningView>("/api/learning");
export const getVendors = () => request<VendorsView>("/api/vendors");

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const runClose = () => post<ActionResult>("/api/close/run");
export const advanceToJanuary = () =>
  post<ActionResult>("/api/close/advance-to-january");
export const resetDemo = () => post<ActionResult>("/api/reset");

export const decideObligation = (
  id: string,
  body: { decision: Decision; notes: string; decided_by?: string },
) => post<ActionResult>(`/api/controller/${encodeURIComponent(id)}/decision`, body);

export const decideRule = (
  id: string,
  action: "approve" | "reject" | "revoke",
  body: { notes: string; decided_by?: string },
) => post<ActionResult>(`/api/learning/${encodeURIComponent(id)}/${action}`, body);
