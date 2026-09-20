/**
 * The six-column track shared by the vendor table's header row and its body
 * rows: vendor, profile, workflow, amount, agent state, overflow. The tracks
 * give way before they let the agent-state column run under the detail rail.
 * Keeping it in one place stops the two grids drifting apart.
 */
export const VENDOR_GRID =
  "grid grid-cols-[minmax(150px,1fr)_minmax(110px,1.05fr)_minmax(140px,168px)_minmax(84px,118px)_minmax(150px,156px)_24px] items-center gap-x-[14px]";
