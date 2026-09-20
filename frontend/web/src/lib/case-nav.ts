/** Every close screen shows one obligation, named by the `o` search param. */
export const CASE_PARAM = "o";

export function caseHref(route: string, obligationId: string | null | undefined): string {
  return obligationId ? `${route}?${CASE_PARAM}=${encodeURIComponent(obligationId)}` : route;
}
