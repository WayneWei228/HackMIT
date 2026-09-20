import { Suspense } from "react";
import { CaseNavigation } from "@/components/close/case-navigation";

export default function CloseLayout({ children }: { children: React.ReactNode }) {
  return <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
    <Suspense><CaseNavigation /></Suspense>
    <div className="flex min-h-0 flex-1 overflow-hidden">{children}</div>
  </div>;
}
