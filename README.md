# CYDRA Web3 — Authorization Security Research Engine

**Evidence-first research software for investigating authorization boundaries in Solidity/EVM contracts.**

> **LLMs propose. Deterministic tools test. Evidence decides.**

CYDRA Web3 is a focused research project for examining whether externally callable, state-changing smart-contract operations enforce the authorization required by their security model. Its first specialty is missing or ineffective authorization. It is not a general-purpose vulnerability scanner, an autonomous exploit agent, or a commercial security product.

## Research question

Can a reproducible, source-grounded analysis pipeline identify authorization boundaries in unfamiliar Solidity projects, construct meaningful local experiments, distinguish vulnerable behaviour from protected controls, and preserve enough evidence for independent reproduction?

A source pattern, static-analysis alert, proposed hypothesis, successful compilation or green CI run is not a finding.

## How the research engine is intended to work

1. **Freeze scope:** record explicit testing permission, target repository, exact commit, source path and environment.
2. **Model the target:** identify externally callable operations, modifiers, call paths and state effects with source-linked provenance.
3. **Form hypotheses:** derive authorization invariants from observed target behaviour; preserve competing explanations and protected surfaces.
4. **Construct experiments:** use grounded preconditions and ABI/project metadata; do not invent constructor values, roles or state.
5. **Execute locally:** preserve tool versions, raw output, source revision and environment details.
6. **Challenge the result:** compare positive and protected negative controls, then use a causal authorization change to test whether the observed outcome depends on the suspected guard.
7. **Reproduce independently:** rerun from a clean state before any finding claim.
8. **Report honestly:** distinguish confirmed, rejected, not selected, blocked, unmeasurable and not-run outcomes.

## Current research boundary

The first milestone is limited to authorization failures involving externally callable, state-changing Solidity/EVM operations.

Out of scope for this milestone: reentrancy, arithmetic, signature replay, oracle manipulation, intent parity, general Web2 testing and broad autonomous live exploitation.

All target campaigns must follow the target programme's explicit scope and rules. Prefer local forks and controlled environments. Do not send transactions to live assets unless the programme expressly permits the exact activity.

## Repository map

| Location | Purpose |
|---|---|
| `PROJECT_BIBLE.md` | Mission, research scope, method and completion contract |
| `AGENTS.md` | Engineering and evidence rules for repository changes |
| `src/cydra/` | Python implementation |
| `tests/` | Regression and control tests |
| `docs/STATUS.md` | Verified project state and next milestone |
| `docs/DEFINITION_OF_DONE.md` | Objective readiness gates |
| `docs/CAMPAIGN_PROTOCOL.md` | Blind campaign, controls and evidence protocol |
| `docs/STAGING_AUDIT.md` | Staging and artifact audit notes |

## Maturity and evidence

The repository contains a substantial Python implementation, regression tests, GitHub Actions workflows and documented campaign experiments. That establishes an active engineering/research codebase, not a completed or independently validated security specialist.

The merged `main` baseline is currently **`cba12e2aee79bae2b6258e0c4d2fa2f75ab41fdf`** (17 October 2026). Draft PR #89, [Wire observation and write-form capabilities](https://github.com/Wonderadroit/Cydra_web3/pull/89), is not merged. Its capability integration must not be described as part of `main` until it is reviewed and merged.

A credible unfamiliar-target result still requires an executed experiment, security-relevant state transition, protected negative control, causal verification, independent reproduction and human review. Historical benchmark matches are controls, not novel discoveries.

See [current status](docs/STATUS.md) for the verified baseline, blockers and next engineering gate.

## Research integrity

- Never invent source locations, functions, roles, state, constructor arguments, transactions, impact or evidence.
- A failed setup is a blocker or unmeasurable experiment, not evidence that authorization is correct or absent.
- Preserve negative results and untested coverage.
- Do not add target-name or function-name special cases to force a benchmark result.
- Do not weaken the finding gate to make CI green.
- Keep the original source repository intact; this repository is a curated specialist implementation.
- Human operators remain responsible for scope, impact assessment and external disclosure.

## Technology

- Python package with a `src/` layout.
- Python 3.10 or later.
- Python standard library for core package dependencies.
- Pytest regression suite.
- Solidity compiler/project tooling and Foundry for supported local campaign execution.

## Project status

**Active research and engineering. Not production-ready. No claim of general vulnerability-detection coverage or guaranteed bounty findings.**

