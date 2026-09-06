"use client";

import Link from "next/link";

import { useDashboard, useTasks } from "@/lib/api";
import { Empty, Metric, StatusBadge } from "@/components/ui";

export default function DashboardPage() {
  const { data: dash } = useDashboard();
  const { data: tasks } = useTasks();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Dashboard</h1>
        <Link href="/tasks/new" className="btn btn-primary">
          New engineering task
        </Link>
      </div>

      {dash && !dash.enough_data && (
        <Empty>
          Not enough completed runs yet to report rates. Metrics appear here once at least
          3 runs finish — nothing on this page is fabricated.
        </Empty>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Metric
          label="Task success"
          value={dash?.task_success_rate != null ? `${Math.round(dash.task_success_rate * 100)}%` : "—"}
          hint={`${dash?.totals.finished_runs ?? 0} finished runs / ${dash?.window_days ?? 30}d`}
        />
        <Metric
          label="Avg latency"
          value={dash?.avg_latency_s != null ? `${dash.avg_latency_s}s` : "—"}
        />
        <Metric
          label="Avg cost"
          value={dash?.avg_cost_usd != null ? `$${dash.avg_cost_usd.toFixed(4)}` : "—"}
        />
        <Metric
          label="High security findings"
          value={String(dash?.security_findings_high ?? 0)}
        />
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-muted">Recent tasks</h2>
        {!tasks?.length ? (
          <Empty>No tasks yet. Connect a repository and create one.</Empty>
        ) : (
          <div className="divide-y divide-border rounded-lg border border-border">
            {tasks.slice(0, 12).map((t) => (
              <Link
                key={t.id}
                href={`/tasks/${t.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-white/5"
              >
                <div>
                  <div className="text-sm">{t.title}</div>
                  <div className="text-xs text-muted">
                    {t.autonomy} · {t.model}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {t.latest_run && (
                    <span className="text-xs text-muted">
                      ${Number(t.latest_run.total_cost_usd).toFixed(4)}
                    </span>
                  )}
                  <StatusBadge status={t.status} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
