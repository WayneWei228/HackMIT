/**
 * The thin edge between this app and the close API.
 *
 * Every screen in the product ships with a synthetic dataset in its route
 * folder (`_data.ts`). The API serves the *same* shape: a JSON object whose
 * keys are that file's exported data-constant names. Nothing here knows what
 * those keys are - `useLiveData` merges whatever arrives over the mock.
 *
 * The app is fully usable with no API running: every call below is allowed to
 * fail, and the caller falls back to the mock.
 */

const DEFAULT_BASE_URL = "http://localhost:8000";

/** Base URL of the close API, without a trailing slash. */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || DEFAULT_BASE_URL
).replace(/\/+$/, "");

/** The eight close screens the API can serve, in chain order. */
export const CLOSE_SCREENS = [
  "ingestion",
  "evidence",
  "detection",
  "invoice-lookup",
  "classification",
  "estimation",
  "outreach",
  "settlement",
] as const;

export type CloseScreen = (typeof CLOSE_SCREENS)[number];

/**
 * A non-2xx answer, carrying the code.
 *
 * A 404 means "no such case" and a connection failure means "no backend";
 * they read very differently to the person on the screen, so the status
 * travels with the error rather than being flattened into a message.
 */
export class HttpError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

/** `GET <base><path>` as JSON. Throws on a non-2xx or on malformed JSON. */
export async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new HttpError(
      response.status,
      `${response.status} ${response.statusText} for ${path}`,
    );
  }
  return (await response.json()) as T;
}

/** `GET /api/cases` -> `{ CASES }`. */
export const casesPath = "/api/cases";

/** `GET /api/vendors` -> `{ VENDORS }`. */
export const vendorsPath = "/api/vendors";

/** `GET /api/journals` - every entry the close posted, scoped by period. */
export const journalsPath = "/api/journals";

/** `GET /api/documents` - every file the close could read, by period. */
export const documentsPath = "/api/documents";

/** `GET /api/health` - used only to tell "API down" from "API said no". */
export const healthPath = "/api/health";

/**
 * Turn the `?case=` query value - `"<period>/<case_key>"`, e.g.
 * `"2026-12/PO-001-001"` - into the screen endpoint for that case.
 *
 * Both segments are encoded on their own, so a case key containing a slash or
 * a space cannot forge a path. Anything that is not exactly two non-empty
 * segments yields `null`, which `useLiveData` reads as "stay on the mock".
 */
export function casePath(
  caseParam: string | null | undefined,
  screen: CloseScreen,
): string | null {
  if (!caseParam) return null;
  const segments = caseParam.split("/");
  if (segments.length !== 2) return null;
  const [period, caseKey] = segments;
  if (!period || !caseKey) return null;
  return `/api/cases/${encodeURIComponent(period)}/${encodeURIComponent(
    caseKey,
  )}/screens/${screen}`;
}

/** `GET /api/cases/{period}/{case_key}` - the case, its documents and log. */
export function caseDetailPath(
  caseParam: string | null | undefined,
): string | null {
  if (!caseParam) return null;
  const segments = caseParam.split("/");
  if (segments.length !== 2) return null;
  const [period, caseKey] = segments;
  if (!period || !caseKey) return null;
  return `/api/cases/${encodeURIComponent(period)}/${encodeURIComponent(
    caseKey,
  )}`;
}

/**
 * `GET /api/cases/{period}/{case_key}/handoff` - the raw JSON every agent read
 * and wrote for the case, each part named after the file it is in.
 */
export function handoffPath(
  caseParam: string | null | undefined,
): string | null {
  const detail = caseDetailPath(caseParam);
  return detail ? `${detail}/handoff` : null;
}

/**
 * `GET /api/story` - one vendor's cases on one timeline, holding only what had
 * happened by the end of `through` (a calendar month, `YYYY-MM`). A `case`
 * stands in for the vendor when the reader arrives from a case's own screen.
 */
export function storyPath(
  vendor: string | null | undefined,
  caseParam: string | null | undefined,
  through: string | null | undefined,
): string | null {
  if (!vendor && !caseParam) return null;
  const query = new URLSearchParams();
  if (vendor) query.set("vendor", vendor);
  else if (caseParam) query.set("case", caseParam);
  if (through) query.set("through", through);
  return `/api/story?${query.toString()}`;
}

/** `GET /api/documents/{doc_id}` - one document's text and extracted record. */
export function documentPath(docId: string | null | undefined): string | null {
  if (!docId) return null;
  return `/api/documents/${encodeURIComponent(docId)}`;
}

/** `GET /api/periods` - every month the run directory knows about. */
export const periodsPath = "/api/periods";

/** `GET /api/run/status` - what the backend is doing right now. */
export const runStatusPath = "/api/run/status";

/** A list endpoint scoped to one month; no period means every month. */
export function withPeriod(path: string, period?: string | null): string {
  if (!period) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}period=${encodeURIComponent(period)}`;
}

export type PostResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; detail: string };

/**
 * `POST <base><path>`, with the API's own refusal preserved.
 *
 * A month that cannot run yet is answered with 400 and a `detail` that says
 * which earlier month has to close first, and a second job with 409. Both are
 * things to show the reader, not exceptions, so they come back as values.
 */
export async function postJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<PostResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      signal,
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (response.ok) return { ok: true, data: payload as T };
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `${response.status} ${response.statusText}`;
    return { ok: false, status: response.status, detail };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}
