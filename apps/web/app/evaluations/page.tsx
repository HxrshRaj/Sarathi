"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, useEvaluations } from "@/lib/api";
import { Empty, StatusBadge } from "@/components/ui";

function pct(v: number | null) {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

export default function EvaluationsPage() {
  const qc = useQueryClient();
  const { data: evals } = useEvaluations();
  const runEval = useMutation({
    mutationFn: () => api.runEvaluation({ benchmark_set: "v1" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evaluations"] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Evaluations</h1>
        <button className="btn btn-primary" disabled={runEval.isPending} onClick={() => runEval.mutate()}>
          Run benchmark set v1
        </button>
      </div>

      {!evals?.length ? (
        <Empty>
          No evaluation runs yet. Each run executes the full pipeline against the seed
          benchmarks and records real deterministic gate results.
        </Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-panel text-left text-xs text-muted">
              <tr>
                <th className="px-3 py-2">When</th>
                <th className="px-3 py-2">Model</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Success</th>
                <th className="px-3 py-2">Tests</th>
                <th className="px-3 py-2">Regr.</th>
                <th className="px-3 py-2">Sec. viol.</th>
                <th className="px-3 py-2">Latency</th>
                <th className="px-3 py-2">Cost</th>
              </tr>
            </thead>
            <tbody>
              {evals.map((e) => (
                <tr key={e.id} className="border-t border-border">
                  <td className="px-3 py-2 text-xs text-muted">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{e.model}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={e.status} />
                    {e.has_regression && <span className="ml-2 text-bad">regression</span>}
                  </td>
                  <td className="px-3 py-2">{pct(e.task_success_rate)}</td>
                  <td className="px-3 py-2">{pct(e.test_pass_rate)}</td>
                  <td className="px-3 py-2">{pct(e.regression_rate)}</td>
                  <td className="px-3 py-2">{pct(e.security_violation_rate)}</td>
                  <td className="px-3 py-2">{e.avg_latency_s != null ? `${e.avg_latency_s}s` : "—"}</td>
                  <td className="px-3 py-2">
                    {e.avg_cost_usd != null ? `$${Number(e.avg_cost_usd).toFixed(4)}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
