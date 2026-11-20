# Architecture

```
Next.js chat UI
      |
FastAPI backend ── Langfuse (tracing, cost, latency)
      |
Agent router (LangGraph)
 ├─ SQL tool        → DuckDB/Postgres (M5 sales, prices, calendar)
 ├─ Doc search tool → BM25 + dense (pgvector) → RRF fusion → reranker
 ├─ Anomaly tool    → Bollinger Band detector        (phase 2)
 └─ Events tool     → recalls, weather, news          (phase 2)
      |
Answer synthesis with citations + guardrails
```

_Expanded as each component is built._
