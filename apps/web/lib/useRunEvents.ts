"use client";

import { useEffect, useRef, useState } from "react";

import type { RunEvent } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export interface StepView {
  seq: number;
  agent: string;
  status: "running" | "succeeded" | "failed";
  toolResults: { tool: string; ok: boolean; summary: string }[];
  budget?: Record<string, unknown>;
}

export function useRunEvents(taskId: string, active: boolean) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [steps, setSteps] = useState<Record<number, StepView>>({});
  const [done, setDone] = useState<null | string>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!active) return;
    setEvents([]);
    setSteps({});
    setDone(null);

    const es = new EventSource(`${BASE}/api/tasks/${taskId}/events`, { withCredentials: true });
    esRef.current = es;

    const handle = (e: MessageEvent) => {
      let ev: RunEvent;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      setEvents((prev) => [...prev, ev]);

      if (ev.type === "step.started" && ev.step_seq != null) {
        setSteps((s) => ({
          ...s,
          [ev.step_seq!]: {
            seq: ev.step_seq!,
            agent: (ev.data.agent as string) ?? ev.agent ?? "step",
            status: "running",
            toolResults: [],
          },
        }));
      }
      if (ev.type === "tool.result" && ev.step_seq != null) {
        setSteps((s) => {
          const cur = s[ev.step_seq!];
          if (!cur) return s;
          return {
            ...s,
            [ev.step_seq!]: {
              ...cur,
              toolResults: [
                ...cur.toolResults,
                {
                  tool: (ev.data.tool as string) ?? "?",
                  ok: Boolean(ev.data.ok),
                  summary: (ev.data.summary as string) ?? "",
                },
              ],
            },
          };
        });
      }
      if (ev.type === "step.finished" && ev.step_seq != null) {
        setSteps((s) => {
          const cur = s[ev.step_seq!];
          if (!cur) return s;
          return {
            ...s,
            [ev.step_seq!]: {
              ...cur,
              status: ev.data.status === "failed" ? "failed" : "succeeded",
              budget: ev.data.budget as Record<string, unknown> | undefined,
            },
          };
        });
      }
      if (["run.finished", "run.failed", "run.cancelled"].includes(ev.type)) {
        setDone(ev.type);
        es.close();
      }
    };

    es.onmessage = handle;
    [
      "run.started",
      "run.finished",
      "run.failed",
      "run.cancelled",
      "step.started",
      "step.finished",
      "step.progress",
      "tool.result",
      "test.run",
      "security.finding",
      "review.completed",
      "awaiting_approval",
    ].forEach((t) => es.addEventListener(t, handle as EventListener));

    es.onerror = () => {
      /* EventSource auto-reconnects; if the run is done we already closed it */
    };

    return () => es.close();
  }, [taskId, active]);

  return { events, steps: Object.values(steps).sort((a, b) => a.seq - b.seq), done };
}
