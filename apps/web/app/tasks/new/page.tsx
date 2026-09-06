"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, useRepositories } from "@/lib/api";
import { Empty } from "@/components/ui";

export default function NewTaskPage() {
  const router = useRouter();
  const { data: repos } = useRepositories();
  const [form, setForm] = useState({
    repository_id: "",
    branch: "main",
    title: "",
    description: "",
    autonomy: "supervised",
    max_iterations: 3,
    run_evaluation: false,
    auto_create_pr: false,
  });

  const create = useMutation({
    mutationFn: () => api.createTask(form),
    onSuccess: (task) => router.push(`/tasks/${task.id}`),
  });

  const ready = repos?.length && form.repository_id && form.title.length >= 3 && form.description.length >= 10;

  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-lg font-semibold">Create engineering task</h1>

      {!repos?.length ? (
        <Empty>Connect and index a repository first.</Empty>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div>
            <label className="label">Repository</label>
            <select
              className="select"
              value={form.repository_id}
              onChange={(e) => setForm({ ...form, repository_id: e.target.value })}
            >
              <option value="">Select…</option>
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name}
                  {r.latest_version?.status === "ready" ? "" : "  (not indexed — retrieval disabled)"}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Branch</label>
              <input
                className="input"
                value={form.branch}
                onChange={(e) => setForm({ ...form, branch: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Model</label>
              <input className="input" value="from server default" disabled />
            </div>
          </div>

          <div>
            <label className="label">Title</label>
            <input
              className="input"
              value={form.title}
              placeholder="Add JWT auth to the API and write tests"
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Task description</label>
            <textarea
              className="textarea min-h-32"
              value={form.description}
              placeholder="Investigate why the checkout endpoint returns 500 and fix it. Add a regression test."
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <p className="mt-1 text-xs text-muted">
              Treated as the engineering instruction. Repository contents are treated as
              untrusted data by the agents.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Autonomy</label>
              <select
                className="select"
                value={form.autonomy}
                onChange={(e) => setForm({ ...form, autonomy: e.target.value })}
              >
                <option value="assist">L1 · Assist (plan only)</option>
                <option value="supervised">L2 · Supervised (edit + test, approve to push)</option>
                <option value="controlled">L3 · Controlled autonomous</option>
              </select>
            </div>
            <div>
              <label className="label">Max repair iterations</label>
              <input
                type="number"
                min={1}
                max={10}
                className="input"
                value={form.max_iterations}
                onChange={(e) => setForm({ ...form, max_iterations: Number(e.target.value) })}
              />
            </div>
          </div>

          <div className="flex gap-6 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.run_evaluation}
                onChange={(e) => setForm({ ...form, run_evaluation: e.target.checked })}
              />
              Run evaluation after
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.auto_create_pr}
                onChange={(e) => setForm({ ...form, auto_create_pr: e.target.checked })}
              />
              Auto-create PR (L3 only)
            </label>
          </div>

          {create.isError && (
            <p className="text-sm text-bad">{(create.error as Error).message}</p>
          )}

          <button className="btn btn-primary" disabled={!ready || create.isPending} type="submit">
            {create.isPending ? "Creating…" : "Create task"}
          </button>
        </form>
      )}
    </div>
  );
}
