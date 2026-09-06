"use client";

import Link from "next/link";

import { useTasks } from "@/lib/api";
import { Empty, StatusBadge } from "@/components/ui";

export default function TasksPage() {
  const { data: tasks } = useTasks();
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Tasks</h1>
        <Link href="/tasks/new" className="btn btn-primary">
          New task
        </Link>
      </div>
      {!tasks?.length ? (
        <Empty>No tasks yet.</Empty>
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border">
          {tasks.map((t) => (
            <Link
              key={t.id}
              href={`/tasks/${t.id}`}
              className="block px-4 py-3 hover:bg-white/5"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm">{t.title}</span>
                <StatusBadge status={t.status} />
              </div>
              <div className="mt-1 text-xs text-muted">
                {t.branch} · {t.autonomy} · {t.model}
                {t.latest_run?.confidence && ` · confidence ${t.latest_run.confidence}`}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
