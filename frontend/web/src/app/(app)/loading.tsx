/** Shown while a screen's data is on its way from the backend. */
export default function AppLoading() {
  return (
    <main className="flex min-w-[760px] flex-1 items-center justify-center">
      <div className="flex items-center gap-[11px] text-ui text-faint-3">
        <span className="h-[9px] w-[9px] rounded-full bg-accent shadow-[var(--shadow-ring)]" />
        Loading the close...
      </div>
    </main>
  );
}
