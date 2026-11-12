# ADR-013: Third-party agent tooling is vendored, pinned and reviewed

- Status: proposed (2026-11-12)

## Context
Claude Code skills, plugins and MCP servers are prompts and scripts that run with full repo
access. The repo already pins GitHub Actions by SHA and applies a 7-day dependency cooldown.
Sessions run in ephemeral cloud containers. Candidate list reviewed on 2026-11-12 (32 repos).

## Decision
- Third-party skills are vendored into `.claude/skills/<name>/` at a pinned commit, with source
  URL, commit SHA and license recorded next to them, and read in full before commit. No
  install-latest, no auto-update.
- Licenses: MIT, Apache-2.0 or BSD only (consistent with ADR-006).
- No MCP server with access to production or customer data. No memory tool that persists session
  content outside the repo (CLAUDE.md rule 2). CLAUDE.md, ADRs and specs are the project memory.
- Adopt only on a concrete need, one tool per PR.

| Tool | Verdict | When | Reason |
|---|---|---|---|
| anthropics/claude-code-action | Adopt | After the data-layer PR | Automated review of auth, RLS, connector and IAM diffs. Official. Pinned by SHA; needs a repo secret. |
| obra/superpowers (subset: test-driven-development, systematic-debugging, verification-before-completion) | Adopt, vendored subset | Start of implementation | Enforces test-first and evidence before "done", matching the definition of done. |
| anthropics/skills (frontend-design), vercel-labs/agent-skills (React and Next.js rules) | Adopt | Web spec, week of 18 Jan | Next.js is the UI stack; nothing to apply before. |
| oraios/serena | Defer | Repo above ~20k lines | Repo has ~50 files; search is enough. |
| HKUDS/LightRAG | Reject for the product | Revisit for "Ask Atesta" (AI-10, v2) | ADR-010 needs every claim cited to a source chunk; graph entity summaries are generated text. Its Postgres graph store needs Apache AGE, not offered on RDS (verify). Extra LLM cost at indexing. |
| thedotmack/claude-mem | Reject | | Local store is lost with each ephemeral container; transcripts may hold customer data. |
| gsd-build/get-shit-done, OthmanAdi/planning-with-files, affaan-m/everything-claude-code | Reject | | Duplicate the spec, ADR and CLAUDE.md flow; more prompt surface, no new capability. |
| Leonxlnx/taste-skill, pbakaus/impeccable, nextlevelbuilder/ui-ux-pro-max-skill, mattpocock/skills | Reject for now | Compare at the web spec | Overlap with the adopted frontend skills. |
| colbymchenry/codegraph, safishamsi/graphify, vitali87/code-graph-rag, yumeiriowl/repo-graphrag-mcp | Reject | | Same need as serena, deferred. |
| czlonkowski/n8n-mcp, supabase/cli, kepano/obsidian-skills | Reject | | Not in the stack. Supabase conflicts with ADR-007 (RDS in eu-south-2). |
| modelcontextprotocol/servers | Defer | | Reference servers; pick one only on a concrete need. |
| Index lists (awesome-claude-code and similar, claude-code-best-practice, awesome-mcp-servers, awesome-claude-skills, antigravity-awesome-skills) | Reference only | | Lists, nothing to install. |

## Consequences
Small, audited agent surface; a tool costs one PR and one read-through to adopt. Some community
productivity gains are given up until a concrete need appears.
