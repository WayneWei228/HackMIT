/** Every close screen shows one obligation, named by the `o` search param. */
export const CASE_PARAM = "o";

export function caseHref(route: string, obligationId: string | null | undefined): string {
  if (!obligationId) return route;
  const [path, hash] = route.split("#", 2);
  const [pathname, query] = path.split("?", 2);
  const params = new URLSearchParams(query);
  params.set(CASE_PARAM, obligationId);
  return `${pathname}?${params}${hash === undefined ? "" : `#${hash}`}`;
}
