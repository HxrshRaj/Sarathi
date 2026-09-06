import { describe, expect, it } from "vitest";

import { classifyDiffLine, diffStats } from "./diff";

describe("classifyDiffLine", () => {
  it("labels hunk headers", () => {
    expect(classifyDiffLine("@@ -1,3 +1,4 @@")).toBe("hunk");
  });
  it("labels file headers as meta not add/del", () => {
    expect(classifyDiffLine("+++ b/app.py")).toBe("meta");
    expect(classifyDiffLine("--- a/app.py")).toBe("meta");
  });
  it("labels additions and removals", () => {
    expect(classifyDiffLine("+  return x")).toBe("add");
    expect(classifyDiffLine("-  return y")).toBe("del");
  });
  it("labels context", () => {
    expect(classifyDiffLine("  unchanged")).toBe("context");
  });
});

describe("diffStats", () => {
  it("counts real add/remove lines only", () => {
    const diff = ["--- a/x", "+++ b/x", "@@ -1 +1,2 @@", "-old", "+new", "+extra", " same"].join("\n");
    expect(diffStats(diff)).toEqual({ added: 2, removed: 1 });
  });
});
