# CYDRA Web3 — Authorization Specialist

CYDRA Web3 is a focused, evidence-first smart-contract research engine. The first milestone specializes in one bug class: missing or ineffective authorization on externally callable state-changing Solidity/EVM operations.

**Current status: migration bootstrap, not yet a runnable specialist.** This branch contains the doctrine, migration ledger, campaign protocol, and binary completion criteria. Core implementation and tests are still being migrated from Cydra_wonder.

## Mission

Given an explicitly authorized, unfamiliar target, CYDRA should independently model the relevant contract behavior, propose authorization hypotheses, run meaningful local experiments, and prove or reject those hypotheses with reproducible evidence.

It must never claim success merely because source compilation or CI passed.

## Start here

1. [Project Bible](PROJECT_BIBLE.md) — purpose, scope, evidence doctrine.
2. [Migration map](MIGRATION_MAP.md) — source modules to preserve and modules to leave behind.
3. [Definition of Done](docs/DEFINITION_OF_DONE.md) — objective completion gate.
4. [Campaign protocol](docs/CAMPAIGN_PROTOCOL.md) — blind testing and controls.
5. [Current status](docs/STATUS.md) — verified baseline and next engineering steps.
6. [Agent instructions](AGENTS.md) — rules for future changes.

## First specialty

Authorization boundary failures only. Other bug classes remain out of the first milestone unless an explicit scope decision changes this.

## Evidence standard

LLMs propose. Deterministic tools test. Evidence decides.

A confirmed finding requires an executed test, a security-relevant state transition, a protected negative control, causal verification, independent reproduction, and human review. A hypothesis is not a finding. An unexecuted experiment is not a negative result. A green workflow is not a security finding.

## Source repository

The migration source is [Wonderadroit/Cydra_wonder](https://github.com/Wonderadroit/Cydra_wonder), inspected at commit 99f43987376a327c423ddde2877ce9995564d254. The source repository is preserved unchanged; this repository is intended to become the clean specialist implementation.
