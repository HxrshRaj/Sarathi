from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


def _benchmarks_root() -> Path:
    env = os.getenv("SARATHI_BENCHMARKS_DIR")
    if env:
        return Path(env)
    # packages/evaluation/benchmarks relative to repo root (…/services/worker/worker/evaluation)
    return Path(__file__).resolve().parents[4] / "packages" / "evaluation" / "benchmarks"


@dataclass(slots=True)
class Benchmark:
    id: str
    path: Path
    category: str
    task: str
    autonomy: str
    max_iterations: int
    weight: float
    criteria: dict
    invariants: dict

    @property
    def repo_dir(self) -> Path:
        return self.path / "repo"

    @property
    def hidden_tests_dir(self) -> Path:
        return self.path / "expectation" / "tests"

    @property
    def rubric(self) -> str:
        rb = self.path / "expectation" / "rubric.md"
        return rb.read_text("utf-8") if rb.exists() else ""


def load_benchmarks(benchmark_set: str) -> list[Benchmark]:
    root = _benchmarks_root()
    if not root.exists():
        return []
    out: list[Benchmark] = []
    for d in sorted(root.iterdir()):
        meta_file = d / "benchmark.yaml"
        if not meta_file.is_file():
            continue
        meta = yaml.safe_load(meta_file.read_text("utf-8")) or {}
        if benchmark_set not in ("all", meta.get("set", "v1")):
            continue
        inv_file = d / "expectation" / "invariants.yaml"
        invariants = yaml.safe_load(inv_file.read_text("utf-8")) if inv_file.is_file() else {}
        out.append(
            Benchmark(
                id=meta.get("id", d.name),
                path=d,
                category=meta.get("category", "unknown"),
                task=meta.get("task", "").strip(),
                autonomy=meta.get("autonomy", "supervised"),
                max_iterations=int(meta.get("max_iterations", 3)),
                weight=float(meta.get("weight", 1.0)),
                criteria=meta.get("criteria", {}),
                invariants=invariants or {},
            )
        )
    return out
