"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { use, useMemo } from "react";

import { api, useDiff, useTask } from "@/lib/api";
import { useRunEvents } from "@/lib/useRunEvents";
import { DiffView } from "@/components/diff-view";
import { Empty, StatusBadge } from "@/components/ui";
import { clsx } from "@/lib/clsx";

export default function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { data: task } = useTask(id);
  const running = task?.status === "running" || task?.status === "queued";
  const { steps, done } = useRunEvents(id, Boolean(task) && running);
  const finished = task && ["awaiting_approval", "completed", "failed", "cancelled"].includes(task.status);
  const { data: diff } = useDiff(id, Boolean(finished));
  const { data: review } = useQuery({
    queryKey: ["review", id],
    queryFn: () => api.review(id),
    enabled: Boolean(finished),
  });

  const run = useMutation({
    mutationFn: () => api.runTask(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", id] }),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelTask(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", id] }),
  });
  const approve = useMutation({
    mutationFn: (createPr: boolean) => api.approve(id, createPr),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", id] }),
  });

  const reviewObj = review?.review as Record<string, unknown> | null | undefined;

  const timeline = useMemo(
    () => (steps.length ? steps : []),
    [steps],
  );

  if (!task) return <Empty>Loading…</Empty>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold">{task.title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{task.description}</p>
          <div className="mt-2 text-xs text-muted">
            {task.branch} · {task.autonomy} · {task.model} · <StatusBadge status={task.status} />
          </div>
        </div>
        <div className="flex gap-2">
          {(task.status === "draft" || task.status === "failed") && (
            <button className="btn btn-primary" disabled={run.isPending} onClick={() => run.mutate()}>
              Run task
            </button>
          )}
          {running && (
            <button className="btn" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel
            </button>
          )}
        </div>
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-muted">Agent run</h2>
        {!running && !timeline.length && !finished ? (
          <Empty>Not started. Press “Run task”.</Empty>
        ) : (
          <ol className="space-y-2">
            {timeline.map((s) => (
              <li key={s.seq} className="rounded-lg border border-border">
                <div className="flex items-center justify-between px-3 py-2">
                  <span className="font-mono text-sm">
                    {s.seq}. {s.agent}
                  </span>
                  <span
                    className={clsx(
                      "font-mono text-xs",
                      s.status === "succeeded" && "text-ok",
                      s.status === "running" && "text-accent",
                      s.status === "failed" && "text-bad",
                    )}
                  >
                    {s.status}
                  </span>
                </div>
                {s.toolResults.length > 0 && (
                  <ul className="border-t border-border px-3 py-2 text-xs">
                    {s.toolResults.map((t, i) => (
                      <li key={i} className="flex gap-2">
                        <span className={t.ok ? "text-ok" : "text-bad"}>{t.ok ? "✓" : "✗"}</span>
                        <span className="font-mono text-muted">{t.tool}</span>
                        <span className="text-muted">{t.summary}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {s.budget && (
                  <div className="border-t border-border px-3 py-1 text-[11px] text-muted">
                    tokens {String(s.budget.input_tokens)}/{String(s.budget.output_tokens)} · $
                    {Number(s.budget.cost_usd ?? 0).toFixed(4)}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
        {done && <p className="mt-2 text-xs text-muted">stream closed: {done}</p>}
      </section>

      {finished && (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-muted">
              Changes {diff ? `(+${diff.total_added} / -${diff.total_removed})` : ""}
            </h2>
            {task.status === "awaiting_approval" && (
              <div className="flex gap-2">
                <button
                  className="btn"
                  disabled={approve.isPending}
                  onClick={() => approve.mutate(false)}
                >
                  Approve (no PR)
                </button>
                <button
                  className="btn btn-primary"
                  disabled={approve.isPending}
                  onClick={() => approve.mutate(true)}
                >
                  Approve &amp; open PR
                </button>
              </div>
            )}
          </div>
          <DiffView files={diff?.files ?? []} />
        </section>
      )}

      {reviewObj && (
        <section className="card space-y-2">
          <h2 className="text-sm font-semibold text-muted">Review</h2>
          <div className="grid grid-cols-3 gap-2 text-sm md:grid-cols-6">
            {["overall_score", "correctness", "security", "maintainability", "testing", "performance"].map(
              (k) => (
                <div key={k}>
                  <div className="text-[11px] uppercase text-muted">{k.replace("_", " ")}</div>
                  <div className="text-lg font-semibold">{String(reviewObj[k] ?? "—")}</div>
                </div>
              ),
            )}
          </div>
          <div className="text-xs">
            production ready:{" "}
            <span className={reviewObj.production_ready ? "text-ok" : "text-bad"}>
              {String(reviewObj.production_ready)}
            </span>
            {reviewObj.escalated_to_human ? (
              <span className="ml-2 text-warn">
                escalated — {String(reviewObj.escalation_reason)}
              </span>
            ) : null}
          </div>
          {Array.isArray(reviewObj.blocking_issues) && reviewObj.blocking_issues.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-bad">
              {(reviewObj.blocking_issues as string[]).map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
