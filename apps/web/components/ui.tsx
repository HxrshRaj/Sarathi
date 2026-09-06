"use client";

import { clsx } from "@/lib/clsx";

export function StatusBadge({ status }: { status: string }) {
  const tone =
    {
      succeeded: "text-ok bg-ok/10",
      completed: "text-ok bg-ok/10",
      ready: "text-ok bg-ok/10",
      running: "text-accent bg-accent/10",
      queued: "text-accent bg-accent/10",
      indexing: "text-accent bg-accent/10",
      awaiting_approval: "text-warn bg-warn/10",
      pending: "text-muted bg-muted/10",
      draft: "text-muted bg-muted/10",
      failed: "text-bad bg-bad/10",
      cancelled: "text-bad bg-bad/10",
    }[status] ?? "text-muted bg-muted/10";
  return (
    <span className={clsx("rounded px-1.5 py-0.5 font-mono text-xs", tone)}>{status}</span>
  );
}

export function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="card text-sm text-muted" role="status">
      {children}
    </div>
  );
}
