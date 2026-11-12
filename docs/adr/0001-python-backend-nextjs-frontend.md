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
