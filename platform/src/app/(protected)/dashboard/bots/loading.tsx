import { Skeleton } from "@/components/ui/skeleton";

export default function BotsLoading() {
  return (
    <div className="space-y-6">
      {/* Overview strip — 3 stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-border bg-bg-card p-4"
          >
            <Skeleton className="h-3 w-20 mb-2" />
            <Skeleton className="h-7 w-12" />
          </div>
        ))}
      </div>

      {/* Bot cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-border bg-bg-card flex flex-col"
          >
            {/* Header */}
            <div className="p-6 pb-4">
              <div className="flex items-start gap-3 mb-3">
                <Skeleton className="h-10 w-10 rounded-lg shrink-0" />
                <div className="space-y-2">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-5 w-16 rounded-full" />
                </div>
              </div>
              <Skeleton className="h-3 w-full" />
              <Skeleton className="mt-1 h-3 w-3/4" />
            </div>

            {/* Stats grid */}
            <div className="px-6 pb-4 grid grid-cols-2 gap-3">
              {Array.from({ length: 4 }).map((_, j) => (
                <div key={j} className="rounded-lg bg-bg-primary/50 p-3">
                  <Skeleton className="h-3 w-14 mb-2" />
                  <Skeleton className="h-4 w-10" />
                </div>
              ))}
            </div>

            {/* Position bar */}
            <div className="px-6 pb-4">
              <div className="flex justify-between mb-2">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-3 w-10" />
              </div>
              <Skeleton className="h-1.5 w-full rounded-full" />
            </div>

            {/* Coins */}
            <div className="px-6 pb-4">
              <Skeleton className="h-3 w-20 mb-2" />
              <div className="flex gap-1.5">
                {Array.from({ length: 4 }).map((_, j) => (
                  <Skeleton key={j} className="h-5 w-12 rounded-full" />
                ))}
              </div>
            </div>

            {/* Footer */}
            <div className="mt-auto border-t border-border p-4 flex items-center justify-between">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-16 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
