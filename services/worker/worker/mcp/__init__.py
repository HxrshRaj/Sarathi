"""Sarathi MCP server.

A genuine Model Context Protocol server (stdio transport) that exposes a subset
of Sarathi's real capabilities as MCP tools:

- ``search_codebase``  — the actual hybrid retrieval pipeline
  (dense pgvector + lexical tsvector + trigram symbol, RRF-fused)
- ``get_repo_structure`` — the real deterministic ``analyze_repo`` scan plus the
  indexed file tree
- ``list_indexed_repositories`` — discovery helper
- ``run_evaluation`` / ``get_evaluation_result`` — enqueue + poll the real
  evaluation harness

Every tool calls the existing worker code paths; nothing is reimplemented.
Run it with ``python -m worker.mcp`` or the ``sarathi-mcp`` console script.
"""
