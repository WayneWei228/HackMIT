import { CASE_PARAM } from "./case-nav";
import { getClose, getObligation } from "./api";
import type { CloseView, ObligationDetail } from "./api-types";

export type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export type LoadedCase =
  | { close: CloseView; detail: ObligationDetail }
  | { close: CloseView; detail: null };

/**
 * The close and the obligation a screen is showing: `?o=<obligation id>`, or the
 * first case of the close. `detail` is null until the December close has opened
 * any obligation. Throws `BackendUnreachableError` when the API is down.
 */
export async function loadCase(searchParams: SearchParams): Promise<LoadedCase> {
  const [close, params] = await Promise.all([getClose(), searchParams]);
  const requested = params[CASE_PARAM];
  const id =
    (typeof requested === "string" ? requested : undefined) ??
    close.cases[0]?.obligation_id;
  if (!id) return { close, detail: null };
  return { close, detail: await getObligation(id) };
}
