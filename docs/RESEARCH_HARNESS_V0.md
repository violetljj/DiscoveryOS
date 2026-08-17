# DiscoveryOS Research Harness V0

## Status

```text
RESEARCH_HARNESS_V0_MECHANICS_READY
STATIC_ALGORITHM_DISCOVERY_PROFILE_AVAILABLE
DIRECT_ADA_EVOX_PLUGIN_COMPOSITION_READY
CROSS_STRATEGY_HANDOFF_PROVENANCE_READY
HARNESS_ADAPTATION_PROTOCOL_ONLY
HYBRID_SEARCH_VALUE_NOT_EVALUATED
DISCOVERYOS_SEARCH_VALUE_NOT_YET_ESTABLISHED
```

V0 is an architectural and mechanics delivery. It does not establish that the
built-in profile outperforms Direct LLM, AdaEvolve, EvoX, a naive ensemble, or
any other baseline. No fresh or sealed scientific asset was opened for this
work.

## Position

DiscoveryOS is an evidence-first algorithm-discovery harness, not a single
algorithm-discovery algorithm. The stable kernel owns the scientific authority
and shared research state. Search behavior is supplied by replaceable plugins.

```text
Frozen authority services
  ProblemContract / evaluator / GateEngine / budget
  Candidate+Evidence Store / Artifact Store / Research Graph
                         │
                 ResearchContext
                         │
                 Research Profile
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   Direct LLM       Ada lineage      EvoX meta-strategy
        └────────────────┼────────────────┘
                         │
                  state router
                         │
             existing unified executor
```

Pi and DeepSeek Harness are architecture references, not runtime dependencies.
The repository does not embed either system and does not make DiscoveryOS a
plugin of either system.

## Kernel and plugin boundary

Authority services are typed `ServiceKey` bindings with `authority=True`.
Every child or isolated context inherits them, and `extend` or `intercept`
fails if a plugin attempts to replace them. V0 authority bindings are:

- frozen `ProblemContract` and its resource budget;
- unified `EvidenceLedger` as Candidate/Evidence Store;
- `ArtifactStore` and `ResearchGraph`;
- frozen evaluator service and `GateEngine`.

Replaceable Search-plane services include provider, strategy operator registry,
base action controller, and the composed research action controller. Context
isolation is same-process composition isolation only. It is not a security
sandbox and grants no protection against a hostile plugin.

## Lifecycle

`ResearchHarness.boot` loads an ordered immutable `ResearchProfile`:

1. record the profile as a HarnessGraph node;
2. validate each plugin's declared service dependencies;
3. activate the plugin and reject undeclared service publication;
4. add the plugin layer without mutating its parent context;
5. publish `PROFILE_READY` only after every plugin succeeds.

If activation fails, already-started plugins are disposed in reverse order and
the profile is never marked ready. Normal teardown also disposes plugins in
reverse order. Lifecycle events are written to the unified ledger.

## Built-in static profile

`algorithm-discovery-v0` loads:

| Order | Plugin | Role | Candidate provenance |
|---:|---|---|---|
| 1 | `direct_llm` | bounded bootstrap proposal | `direct_llm_strategy_v1` |
| 2 | `ada_lineage` | promising-lineage refinement | `ada_lineage_strategy_v1` |
| 3 | `evox_meta_strategy` | stagnation-triggered structural revision | `evox_meta_strategy_v1` |
| 4 | `state_router` | deterministic state-to-strategy routing | controller digest |

The names describe imported mechanism roles, not complete official-runtime
ports. The plugins reuse DiscoveryOS `LocalPatchOperator` and
`StructuralRewriteOperator`, and every candidate remains a DiscoveryOS
`CandidateSpec` evaluated by the frozen DiscoveryOS evaluator.

Routing V0 is deliberately small:

```text
first generative step                 -> Direct LLM
authorized non-stagnant refinement    -> Ada lineage
authorized structural escape          -> EvoX meta-strategy
EvoX result followed by refinement    -> EvoX -> Ada cross-seed
Ada/Direct lineage followed by escape -> lineage -> EvoX cross-seed
replicate / promote / stop            -> existing deterministic authority
```

The router cannot authorize an action rejected by the base controller. Budget
preflight, evidence uncertainty, fidelity promotion, parent eligibility,
stagnation prerequisites, and stop behavior remain bound to the existing
replayable controller.

## AlgorithmGraph and HarnessGraph

Candidate ownership is unified. `operator_id` and `strategy_id` are provenance,
not separate populations. When a generated candidate changes strategy, the
ledger records `CROSS_SEEDED_TO` plus a `HARNESS_STRATEGY_HANDOFF` event.

Profiles are content-addressed HarnessGraph nodes. A future profile revision
must name its parent and revision reason and is linked by `HARNESS_REVISED_TO`.
V0 can represent this graph but does not automatically propose, select, or
deploy profile revisions. `adaptive=False` is the built-in default.

## Runnable inspection

```powershell
$env:PYTHONPATH = "src"
python -m discoveryos harness-profile-show
python -m unittest tests.test_research_harness -v
```

The profile command performs no model call, evaluation, plugin boot, or
scientific asset consumption.

## Next evidence gate

Before adaptive harness work, a separate protocol must compare matched-resource
arms on eligible development assets:

```text
Direct/Ada baseline
EvoX baseline
naive Ada + EvoX parallel split
static DiscoveryOS Research Harness V0
```

Tokens, evaluator calls, CPU/GPU/device time, wall envelope, model/settings,
task identity, evaluator regime, and winner rule must be frozen and matched.
Only a positive static-composition result can authorize an adaptive-profile
comparison. Harness evolution then requires a separately frozen feedback signal,
profile mutation space, selection rule, rollback rule, and claim ceiling.

## Architecture references

- Pi minimal coding harness and extension model:
  <https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md>
- DeepSeek Harness plugin architecture and preview warning:
  <https://github.com/deepseek-ai/deepseek-harness>
- DeepSeek Harness scoped context lifecycle note:
  <https://github.com/deepseek-ai/deepseek-harness/blob/master/.agents/notes/implemented/architecture/2026-07-08-agent-scope-contexts.md>
- Hierarchical Self-Improvement feedback/backbone bounds:
  <https://arxiv.org/abs/2608.08466>
