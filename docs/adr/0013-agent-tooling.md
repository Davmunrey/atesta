# ADR-013: Third-party agent tooling is vendored, pinned and reviewed

- Status: accepted (2026-11-12)

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
| anthropics/claude-code-action | Deferred by the owner (2026-11-13) | When the owner adds the API key secret | Automated review of auth, RLS, connector and IAM diffs. Official. Pinned by SHA; needs a repo secret. Adversarial review workflows cover this meanwhile. |
| obra/superpowers (subset: test-driven-development, systematic-debugging, verification-before-completion) | Adopted 2026-11-13, vendored at 22f0b46 (MIT) | Done | Enforces test-first and evidence before "done", matching the definition of done. See `.claude/skills/VENDORED.md`. |
| morluto/rea (npm `rea-agents`) | Adopted 2026-11-14 at the owner's request, pinned 6.8.0 (MIT); process capture only | Done | `capture-process` and `compare-process-captures` record each verification run (exit, terminal output, process cleanup) as Evidence and compare red and green runs, the verification rules in CLAUDE.md. An npm CLI, not a skill: installed per session outside the repo with `--ignore-scripts` and `--before` seven days back (the dependency cooldown), never vendored, no MCP registration, no reverse-engineering providers. Not a sandbox: the command runs with the session's permissions and REA does not record the inherited environment. |
| anthropics/skills (frontend-design), vercel-labs/agent-skills (React and Next.js rules, client subset) | Adopted 2026-11-13, vendored at 41bbe19 (Apache-2.0) and 1a2c79d (MIT) | Done | Next.js is the UI stack. Server rules left out: the static export has no server runtime. See `.claude/skills/VENDORED.md`. |
| oraios/serena | Defer, license-blocked | Repo above ~20k lines | Repo has ~50 files; search is enough. v2.0.0 and later are GPL-3.0-or-later (only the SolidLSP library stays MIT), which fails the license rule above. At the trigger, adopt only after amending this ADR. |
| HKUDS/LightRAG | Reject for the product | Revisit for "Ask Atesta" (AI-10, v2) | ADR-010 needs every claim cited to a source chunk; graph entity summaries are generated text. Its Postgres graph store needs Apache AGE, which RDS for PostgreSQL does not offer (confirmed against the RDS extension list in the 2026-11-13 review; recheck at the v2 revisit). Extra LLM cost at indexing. |
| thedotmack/claude-mem | Reject | | Local store is lost with each ephemeral container; transcripts may hold customer data. |
| gsd-build/get-shit-done, OthmanAdi/planning-with-files, affaan-m/everything-claude-code | Reject | | Duplicate the spec, ADR and CLAUDE.md flow; more prompt surface, no new capability. |
| pbakaus/impeccable (text subset), GoogleChrome/modern-web-guidance (text subset) | Adopted 2026-11-22 at the owner's request ("usa impeccable, usa taste skill, usa modern-web-guidance"), vendored at f56335b (Apache-2.0) and 4dd9683 (Apache-2.0) | Done | App UI design and critique (impeccable, Operate mode) and modern platform patterns (modern-web-guidance). Scripts and `npx @latest` are left out: no download or install at use time. See `.claude/skills/VENDORED.md`. |
| Leonxlnx/taste-skill | Adopted 2026-11-22 at the owner's request, for the marketing landing page only (MIT) | Done 2026-11-23, text subset at f6b7657 without the `Stop` hook | Its scope is marketing websites (photographs, hero, effects). Vendored at a pinned commit when that work starts, without its `Stop` hook scripts unless they are reviewed then. |
| nextlevelbuilder/ui-ux-pro-max-skill, mattpocock/skills | Reject for now | Compare at the web spec | Overlap with the adopted frontend skills. |
| colbymchenry/codegraph, safishamsi/graphify, vitali87/code-graph-rag, yumeiriowl/repo-graphrag-mcp | Reject | | Same need as serena, deferred. Recheck each license if the serena trigger fires. |
| czlonkowski/n8n-mcp, supabase/cli, kepano/obsidian-skills | Reject | | Not in the stack. Supabase conflicts with ADR-007 (RDS in eu-south-2). |
| modelcontextprotocol/servers | Defer | | Reference servers; pick one only on a concrete need. |
| Index lists (awesome-claude-code and similar, claude-code-best-practice, awesome-mcp-servers, awesome-claude-skills, antigravity-awesome-skills) | Reference only | | Lists, nothing to install. |

## Consequences
Small, audited agent surface; a tool costs one PR and one read-through to adopt. Some community
productivity gains are given up until a concrete need appears.
