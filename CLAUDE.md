# Repository Guide for AI Assistants

This file orients future sessions working on this codebase. **The
authoritative contracts live in `docs/specs/` (v1.0 Accepted).** Code is an
implementation of those specs. If implementation and spec disagree, treat
the spec as the source of truth and fix the code — or, if the spec needs
revision, file it under "implementation-phase findings" in
`docs/specs/README.md` and propose a v1.1 amendment.

## What this is

NPU simulation platform implementing the v1.0 spec set:

- **SPEC-001** IModule contract (registration, capability, ports, lifecycle)
- **SPEC-002** Backpressure protocol (ITransportPort, stall reporting, tracer,
  invariants)
- **SPEC-003** Architecture description DSL (YAML, base+overrides, 9-phase
  elaborator)
- **SPEC-004** Functional simulation interface (INumericalModel, comparison)
- **ADR-001** Six key technical decisions
- **ADR-002** Module identity criteria (new IModule subclass vs. capability flag)

Start by reading `docs/specs/README.md`.

## Layout

```
.github/workflows/ci.yml     pytest matrix on push / PR
docs/specs/                  v1.0 Accepted spec set + reviews
npu_sim/
  interfaces/                pure ABCs mirroring SPEC-001/002/004
  core/                      ModuleRegistry, NumericalModelRegistry, errors
  architecture/              DSL loader / overrides / 9-phase Elaborator / SimpleClock
  runtime/                   Fifo / TlmConnection / TlmPorts / Scheduler / Tracer / Invariants
  evaluation/                run_simulation + compare(baseline, variant)
  reporting/                 Markdown renderers
  modules/
    dummy/                   self-test fixture
    probe/                   Producer / Consumer / Passthrough / Merger (test rig)
  cli.py / __main__.py       `python -m npu_sim {list-modules,simulate,compare}`
tests/                       unit + integration; fixtures under tests/fixtures/
```

## How to run things

```bash
# install + test
pip install -e .[dev]
pytest tests/

# CLI
python -m npu_sim list-modules
python -m npu_sim simulate tests/fixtures/architectures/usecase_baseline.yaml
python -m npu_sim compare tests/fixtures/architectures/usecase_baseline.yaml \
                          tests/fixtures/architectures/usecase_variant_slow_cons.yaml
```

Test suite must stay fast. Last commit reported ~1.0 s for the full suite.
If you add slow tests, ask before merging — fast feedback is part of the
platform's value proposition.

## When making changes

- **Edit the spec first** if you're changing a contract (anything in
  `interfaces/`, IModule semantics, stall attribution rules, DSL grammar,
  invariant set). A code change without a spec change for these is a bug.
- **Edit code only** if you're implementing or fixing inside an existing
  contract.
- Tests for every spec rule. Each spec § number should be referenced in
  test docstrings or comments — `grep` should find every rule and its test.
- Public APIs use dataclasses (frozen where possible), abstract base
  classes, and explicit Optional. Avoid `**kwargs` smuggling at boundaries.
- The Python-only runtime (`runtime/`) is a stand-in for the SystemC kernel
  per ADR-001.1. Keep it semantic-equivalent — anything that works here
  must work the same way under SystemC later.

## How to add a new module

1. Decide if it's a new IModule subclass or a capability flag on an
   existing one. **ADR-002** has the 6-rule decision matrix.
2. If new: add `npu_sim/modules/<area>/<module>.py`, decorate with
   `@ModuleRegistry.register`. Implement the SPEC-001 §3 contract:
   `module_type`, `module_version`, `config_schema`, `declared_capabilities`,
   `port_specs`, `bind_services`, `configure`, `reset`, `destroy`,
   `input_ports`, `output_ports`, `active_capabilities`, `can_execute`,
   `estimate_latency`, `estimate_energy`, `snapshot_state`.
3. `module_type()` must match `^[A-Z][A-Za-z0-9]{0,23}$` (SPEC-001 §3.1.1).
4. If the module participates in the runtime (sends/receives tokens),
   expose a `behavior()` generator and use `TlmOutputPort.send` and
   `TlmInputPort.try_receive` — see `modules/probe/` for live examples.
5. If supplying a functional model, add `INumericalModel` subclass under
   the same module package, decorated with `@NumericalModelRegistry.register`.
6. Add unit + conformance tests mirroring `tests/unit/test_dummy_module.py`
   (SPEC-001 §6) and `tests/integration/test_transport_backpressure.py`
   (SPEC-002 §6).
7. Register it in `npu_sim/modules/<area>/__init__.py` and ensure
   `npu_sim/modules/__init__.py` imports the package so registration
   happens at process startup.

## How to add a new DSL feature

Update SPEC-003 (and the JSON Schema in `npu_sim/architecture/dsl_schema.py`),
then implement in `npu_sim/architecture/overrides.py` or `elaborator.py`.
Each new feature needs a test fixture under
`tests/fixtures/architectures/` and a test in
`tests/integration/test_elaborator.py`.

## Commit conventions

- One concern per commit. Don't bundle multiple subsystems.
- Commit message body explains the *why* and references spec sections.
- Reference spec § numbers in commit subjects when applicable.

## PR conventions

- PR #2 is the active development PR for the spec-driven implementation
  rollout. Push commits to that branch (`claude/confident-albattani-RVyZ9`)
  to update it.
- Don't create new PRs unless the user asks. Don't merge.
- CI runs pytest on Python 3.11 and 3.12. Both must pass.

## v1.1 candidate findings

Implementation-phase issues that hint at v1.0 spec gaps are tracked in
`docs/specs/README.md` under "implementation-phase findings". Add to that
list whenever you discover a case where the spec is ambiguous, missing, or
contradicted by what makes sense in practice. Do not silently fix v1.0
specs — promote to v1.1 candidate, leave a comment in code, file it in
the README list.

## What this platform is NOT

- A SystemC simulator yet. Phase 0 / SystemC integration is deferred per
  ADR-001.1; the Python runtime in `runtime/` carries semantic-equivalent
  contracts for now.
- A trained NPU model. SPEC-004 functional sim runs structural data flow,
  not numerical training.
- Production-grade. Coverage is good for the v1.0 contracts but real NPU
  modules (DAGC, DSB, MAC...) haven't been implemented yet.
