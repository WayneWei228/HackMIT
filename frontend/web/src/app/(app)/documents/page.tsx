import { Suspense } from "react";

import { DocumentsRoute } from "./_components/documents-route";
import { DocumentsScreen } from "./_components/documents-screen";

export const metadata = {
  title: "Documents - TrueUp",
};

/**
 * The files the close read for the selected month. The shell and sidebar come
 * from `(app)/layout.tsx`.
 *
 * The month lives in `?period=`, so the component that reads it sits under a
 * `Suspense` boundary - `useSearchParams` suspends during the prerender, and
 * the fallback is the same screen with no month, which resolves to whatever
 * the backend calls current.
 */
export default function DocumentsPage() {
  return (
    <main className="flex min-w-[900px] flex-1 flex-col overflow-hidden leading-[normal]">
      <Suspense fallback={<DocumentsScreen periodParam={null} />}>
        <DocumentsRoute />
      </Suspense>
    </main>
  );
}
