"use client";

import { useMe } from "@/lib/api";

export function UserBadge() {
  const { data: me, isError } = useMe();
  if (isError) {
    return (
      <a className="btn" href="/api/auth/github/start">
        Sign in with GitHub
      </a>
    );
  }
  if (!me) return <span className="text-xs text-muted">…</span>;
  return (
    <div className="flex items-center gap-2 text-sm">
      {me.auth_mode === "dev" && (
        <span className="rounded bg-warn/15 px-1.5 py-0.5 text-xs text-warn">dev auth</span>
      )}
      <span className="text-muted">{me.login}</span>
      {me.auth_mode === "github" && (
        <form action="/api/auth/logout" method="post">
          <button className="text-xs text-muted hover:text-white" type="submit">
            logout
          </button>
        </form>
      )}
    </div>
  );
}
