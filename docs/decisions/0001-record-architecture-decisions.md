# 1. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

As a team we make decisions throughout the project — which framework, which
database, how to structure a feature, what trade-off to accept. Three weeks later
nobody remembers *why*, and we re-argue it or accidentally undo it.

## Decision

We record every notable decision as a short **Architecture Decision Record (ADR)**
in this folder, one file per decision, numbered in order:
`0002-use-postgres.md`, `0003-...`, and so on.

Each ADR has four parts: **Context** (what forced the decision), **Decision**
(what we chose), **Status** (Proposed / Accepted / Superseded), and
**Consequences** (what gets easier and what gets harder).

An ADR is short — half a page. It is not documentation of *how* something works
(that goes in `architecture.md`); it's a record of *why we chose* it.

## Consequences

- New teammates can read the ADRs and understand the project's reasoning.
- We stop re-litigating settled decisions.
- It costs ~5 minutes per real decision. Worth it.

---

> **How to add one:** copy `TEMPLATE.md` to the next number, fill it in, commit
> it in the same PR as the change it describes.
