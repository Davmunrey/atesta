# ADR-001: Python backend, Next.js frontend

- Status: accepted (2026-11-12)

## Context
Scanning, cloud SDKs (Microsoft Graph, Google, AWS), Prowler and AI tooling are Python-native.
One builder, 10-12 h/week, working with Claude Code.

## Decision
Python 3.12 + FastAPI for all server-side code. Next.js + TypeScript only for the UI, with a
typed client generated from OpenAPI.

## Consequences
Fastest path to working connectors. Two languages to maintain; the OpenAPI contract keeps them
in sync. Fallback if time is short: Django + HTMX.

## Amendment 1 (owner decision 2026-11-23, #298): Python 3.13

Every Python runtime and tool moves from 3.12 to 3.13 together: `requires-python`, mypy and ruff
targets, CI, both image bases (one digest) and the scanner's hash-locked requirements. 3.13 is
the newest Python that Prowler allows (`>=3.10,<3.14`). A Python minor is always a planned upgrade
of all of them at once, never a single Dependabot bump.
