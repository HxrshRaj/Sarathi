"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, useRepositories } from "@/lib/api";
import { Empty, StatusBadge } from "@/components/ui";

export default function RepositoriesPage() {
  const qc = useQueryClient();
  const { data: connected } = useRepositories();
  const { data: remote, isError: remoteError } = useQuery({
    queryKey: ["github-repos"],
    queryFn: api.githubRepos,
    retry: false,
  });

  const connect = useMutation({
    mutationFn: (id: number) => api.connectRepo(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repositories"] }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Repositories</h1>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-muted">Connected</h2>
        {!connected?.length ? (
          <Empty>No repositories connected yet.</Empty>
        ) : (
          <div className="space-y-2">
            {connected.map((r) => (
              <RepoRow key={r.id} repo={r} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-muted">From GitHub</h2>
        {remoteError ? (
          <Empty>
            GitHub isn&apos;t linked on this session. Sign in with GitHub (top right) to list
            and connect repositories.
          </Empty>
        ) : !remote ? (
          <Empty>Loading…</Empty>
        ) : (
          <div className="max-h-80 space-y-1 overflow-auto">
            {remote.map((r) => (
              <div
                key={r.github_repo_id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <span className="font-mono">{r.full_name}</span>
                <button
                  className="btn"
                  disabled={connect.isPending}
                  onClick={() => connect.mutate(r.github_repo_id)}
                >
                  Connect
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RepoRow({ repo }: { repo: import("@/lib/types").Repository }) {
  const qc = useQueryClient();
  const [branch, setBranch] = useState(repo.default_branch);
  const index = useMutation({
    mutationFn: () => api.indexRepo(repo.id, branch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repositories"] }),
  });
  return (
    <div className="card flex items-center justify-between">
      <div>
        <div className="font-mono text-sm">{repo.full_name}</div>
        <div className="text-xs text-muted">
          {repo.latest_version ? (
            <>
              indexed <StatusBadge status={repo.latest_version.status} /> ·{" "}
              {repo.latest_version.file_count} files · {repo.latest_version.chunk_count} chunks
            </>
          ) : (
            "not indexed"
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input
          className="input w-32"
          value={branch}
          onChange={(e) => setBranch(e.target.value)}
        />
        <button className="btn" disabled={index.isPending} onClick={() => index.mutate()}>
          {index.isPending ? "Indexing…" : "Index"}
        </button>
      </div>
    </div>
  );
}
