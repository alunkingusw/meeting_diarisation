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
The synthetic source records, VTT files, known speaker metrics, project aggregates, and gold claim
evidence IDs are in [`fixtures/query_agent_synthetic`](../backend/tests/fixtures/query_agent_synthetic/manifest.json).
Gold data is explicitly synthetic; no model-generated outputs are pre-filled or presented as
observed results.

Validate the fixtures without Ollama or vector embeddings:

```bash
python -m pytest backend/tests/test_query_agent_synthetic_dataset.py -q
```

The fixture validation runs the production VTT parser/chunker/statistics code and checks the
structured GitHub/Trello counts from the manifest. It does not yet seed PostgreSQL/Chroma or capture
model answers.

## Live Current-System Capture

An opt-in integration test seeds a disposable PostgreSQL test database and temporary Chroma
collection, calls the existing conversation, GitHub, Trello, and unified query APIs using the real
Ollama client, and writes observed responses to an explicit output path. The transcript cases use
date-bounded complete-window retrieval; this first baseline does not measure vector similarity
ranking. Three email-intent/partial-failure cases are not captured by this API-only run.

```bash
OLLAMA_BASE_URL=http://192.168.68.115:11434 \
RUN_QUERY_AGENT_LIVE_BASELINE=1 \
QUERY_AGENT_BASELINE_OUTPUT=backend/tests/fixtures/query_agent_synthetic/baseline_outputs.json \
python -m pytest backend/tests/test_query_agent_live_baseline.py -q -s
```

The output contains actual observed model responses and evidence; keep it distinct from the
synthetic expected claims in `manifest.json`. Review the artifact before treating it as a paper
baseline. The test requires a working Docker daemon and does not alter persistent application data.

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

The pre-fix capture is retained at
[`baseline_outputs.json`](../backend/tests/fixtures/query_agent_synthetic/baseline_outputs.json).
The post-fix capture is
[`after_scope_stats_fixes.json`](../backend/tests/fixtures/query_agent_synthetic/after_scope_stats_fixes.json).
Both use `llama3.1:8b` digest
`46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`. The post-fix capture records
the request payloads, prompt hashes, retrieved evidence, and gold comparisons. It was captured
cleanly at revision `139770001ff505b0ecf16f8c357f155137e9320c`, before the specialist and parent
query-agent commits. It is a valid pre-parent baseline, but not a live evaluation of the current
parent workflow.

The current-parent capture is
[`current_parent_reviewed.json`](../backend/tests/fixtures/query_agent_synthetic/current_parent_reviewed.json).
It was captured cleanly on 2026-10-13 against revision `842ac4e23e205bf5f35a16b1a8dddc294e2b3447` using
`llama3.1:8b` digest
`46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` (`Q4_K_M`). The capture
includes Python/dependency versions, effective retrieval settings, prompt hashes, and the
`deterministic_source_sections_v1` composition strategy. It records `working_tree_dirty: false` and
is the clean current-parent synthetic API baseline for this revision.

### Gap Status

- **Fixture truth and numeric comparisons: pass.** Offline fixture tests validate VTT statistics
  and project aggregates. All four current-parent gold comparisons pass: September GitHub/Trello
  totals and contributors, unified GitHub totals, and transcript speaker duration/share.
- **Source selection, attribution, and citations: pass on the synthetic current-parent run.** The
  cross-source request selected conversation and GitHub, returned the expected evidence set, and
  included every expected stable evidence ID. Multi-source answers now preserve the specialists'
  answers in deterministic source sections instead of asking another model to rewrite their facts.
- **Partial-source behavior: pass live.** With Trello deliberately unlinked, the API returned the
  transcript findings and an explicit Trello-unavailable notice; the failing source was not treated
  as evidence of absence.
- **Email trust boundaries: pass offline; email intent is intentionally not evaluated live.** The
  sender chose not to include live email-intent model scoring. Deterministic authentication,
  validation, prompt-injection, cancellation, and API-parity tests remain the gate for that path.
- **Not captured live:** authorization ambiguity and unsupported email intent. These are application
  authorization/parser concerns, have offline coverage, and are intentionally outside this live
  model evaluation.
- **Still open:** the transcript fixture uses date-bounded complete-window retrieval; its zero
  vectors are not used for similarity ranking, so semantic retrieval quality, latency, and resource
  use need separate evaluation. The clean synthetic baseline does not certify those dimensions.

Keep the pre-fix, pre-parent, and current-parent snapshots separate. The current live test is
`backend/tests/test_query_agent_live_baseline.py`; it asserts numeric gold, selected sources,
stable cross-source citations, and partial-source degradation before writing the artifact.