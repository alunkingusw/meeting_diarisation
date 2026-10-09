# Query Agent Contracts And Evaluation

Phase 1 working artifact for the [NLP agent architecture roadmap](roadmap.md). These contracts
and cases define the target boundary; they do not imply that the specialist agents or tools are
already wired into the API.

## Contract

The initial Pydantic contracts live in
[`query_agent_schemas.py`](../backend/engine/query_agent_schemas.py):

- `SpecialistQueryInput` contains only the natural-language question and user-requested filters.
  It forbids extra fields, including `group_id` and identity fields.
- `TrustedQueryContext` is supplied by application code after authentication and authorization.
  It carries the user, group, and allowed source set; it is immutable and is never model-generated.
- `SpecialistQueryResult` carries the source answer, cited evidence, structured quantitative facts,
  errors, model ID, and retrieval metadata.
- `QuantitativeFact` requires a numeric value, unit, aggregation scope, provenance, and completeness
  (`complete`, `sampled`, or `unknown`). The parent must not convert sampled evidence into a
  complete count.

Source-specific tools should accept question/filters and receive trusted context through the
application's runtime binding. They must not accept credentials, arbitrary group IDs, URLs, or
write operations from model arguments.

## Evaluation Cases

The machine-readable starter set is
[`query_agent_eval_cases.json`](../backend/tests/query_agent_eval_cases.json). It covers qualitative
and quantitative single-source queries, a mixed transcript question, cross-source composition,
authorization ambiguity, unsupported requests, empty evidence, and partial source failure.
Expected metrics and behavioral checks are specified, but no answers or evidence are fabricated.

For each executed case, record:

- case ID, code revision, timestamp, and effective configuration;
- selected sources and any clarification decision;
- quantitative facts with scope, unit, provenance, and completeness;
- evidence IDs, source metadata, retrieval scores, and truncation/completeness flags;
- generated answer, model identifier, prompt version, latency, and source errors.

Score source selection, evidence relevance, factual support, citation correctness, numeric exactness,
scope/units, unsupported claims, partial-failure behavior, latency, and resource use. Numerical
checks should compare against deterministic fixture truth, not a second LLM judgment.

## Reproducibility Record

Current repository defaults and declared pins at Phase 1:

| Component | Current setting |
| --- | --- |
| Ollama model | `llama3.1:8b` |
| Ollama temperature | `0.2` |
| Transcript embedding model | `all-MiniLM-L6-v2` |
| Transcript embedding device | `cpu` |
| Retrieval top-k | `8` |
| Maximum prompt context | `24000` characters |
| Project complete-window limit | `50` database rows |
| Transcript complete-window limit | `80` chunks |
| ChromaDB | `1.5.9` |
| LangChain Core / Chroma adapter | `1.6.3` / `0.2.6` |
| LangGraph | `1.2.11` |
| Sentence Transformers | `3.1.1` |
| Pydantic | Unpinned in `requirements.txt`; record and pin the effective version for evaluation runs |

Settings can be overridden by deployment environment. A baseline run must therefore record the
effective values, not only these defaults. The Ollama tag and embedding model name are not immutable
artifact revisions in the current configuration; record their resolved model/revision or digest
before claiming exact reproducibility.

## Baseline Status

The cases and capture format are ready, but current answer/evidence snapshots have not been
captured. That requires a seeded PostgreSQL/Chroma dataset and reachable Ollama model. The local
backend test fixture currently requires Docker for PostgreSQL; if that runtime is unavailable,
record the blocker and do not substitute invented answers. Capture the baseline before Phase 2
changes per-source query behavior.