"use client";

import { useState } from "react";

import type { FileChange } from "@/lib/types";
import { clsx } from "@/lib/clsx";

function DiffBody({ diff }: { diff: string }) {
  return (
    <pre className="overflow-x-auto bg-bg p-3 font-mono text-xs leading-5">
      {diff.split("\n").map((line, i) => {
        const cls =
          line.startsWith("+") && !line.startsWith("+++")
            ? "diff-add"
            : line.startsWith("-") && !line.startsWith("---")
              ? "diff-del"
              : line.startsWith("@@")
                ? "text-accent"
                : "text-muted";
        return (
          <div key={i} className={clsx("whitespace-pre", cls)}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

export function DiffView({ files }: { files: FileChange[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>(
    Object.fromEntries(files.map((f) => [f.path, true])),
  );
  if (!files.length) {
    return <div className="card text-sm text-muted">No file changes.</div>;
  }
  return (
    <div className="space-y-3">
      {files.map((f) => (
        <div key={f.path} className="overflow-hidden rounded-lg border border-border">
          <button
            className="flex w-full items-center justify-between bg-panel px-3 py-2 text-left text-sm"
            onClick={() => setOpen((o) => ({ ...o, [f.path]: !o[f.path] }))}
          >
            <span className="font-mono">{f.path}</span>
            <span className="text-xs">
              <span className="text-ok">+{f.lines_added}</span>{" "}
              <span className="text-bad">-{f.lines_removed}</span>{" "}
              <span className="text-muted">· {f.change_type}</span>
            </span>
          </button>
          {open[f.path] && <DiffBody diff={f.diff} />}
        </div>
      ))}
    </div>
  );
}
