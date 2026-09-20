import { routes } from "@/lib/routes";

/** The story page's own address: a vendor, cut at a month. */
export function storyHref(vendor: string, through: string | null): string {
  const query = new URLSearchParams({ vendor });
  if (through) query.set("through", through);
  return `${routes.story}?${query.toString()}`;
}
