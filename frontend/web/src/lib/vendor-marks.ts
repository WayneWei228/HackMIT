/** A stable monogram colour index for a vendor, so it looks the same on every screen. */
export function markIndex(vendorId: string, palette: number): number {
  let sum = 0;
  for (const char of vendorId) sum += char.charCodeAt(0);
  return sum % palette;
}
