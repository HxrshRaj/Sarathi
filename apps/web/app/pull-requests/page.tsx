"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Empty, StatusBadge } from "@/components/ui";

export default function PullRequestsPage() {
  const { data: prs } = useQuery({ queryKey: ["prs"], queryFn: api.pullRequests, refetchInterval: 8000 });
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Pull Requests</h1>
      {!prs?.length ? (
        <Empty>No pull requests created by CodePilot yet.</Empty>
      ) : (
        <div className="space-y-2">
          {prs.map((pr) => (
            <div key={String(pr.id)} className="card">
              <div className="flex items-center justify-between">
                <span className="text-sm">{String(pr.title)}</span>
                <StatusBadge status={String(pr.state)} />
              </div>
              <div className="mt-1 text-xs text-muted">
                {String(pr.branch)} → {String(pr.base)}
                {pr.github_pr_url ? (
                  <>
                    {" · "}
                    <a className="text-accent" href={String(pr.github_pr_url)} target="_blank" rel="noreferrer">
                      #{String(pr.github_pr_number)}
                    </a>
                  </>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
