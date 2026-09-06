"use client";

import { useMe } from "@/lib/api";
import { Empty } from "@/components/ui";

export default function SettingsPage() {
  const { data: me } = useMe();
  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-lg font-semibold">Settings</h1>
      {!me ? (
        <Empty>Not signed in.</Empty>
      ) : (
        <div className="card space-y-2 text-sm">
          <Row k="User" v={me.login} />
          <Row k="Auth mode" v={me.auth_mode} />
          <Row k="Default autonomy" v={me.default_autonomy} />
        </div>
      )}
      <div className="card text-xs text-muted">
        Run limits (max tokens / cost / iterations / runtime), sandbox limits, LLM
        provider and GitHub OAuth are configured server-side via environment
        variables. See <span className="font-mono">.env.example</span>.
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className="font-mono">{v}</span>
    </div>
  );
}
