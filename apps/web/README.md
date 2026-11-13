# apps/web

Next.js static export (App Router, TypeScript strict, Tailwind CSS). Spec:
`docs/specs/web-shell.md`. No Node server in production: CloudFront serves `out/` and routes
`/api/*` and `/auth/*` to the API.

```bash
pnpm install          # pnpm 10, minimumReleaseAge 7 days (pnpm-workspace.yaml)
pnpm dev              # http://localhost:3000; /api and /auth rewritten to ATESTA_API_URL (default :8000)
pnpm test             # vitest unit tests
pnpm typecheck && pnpm lint
pnpm build            # static export to out/
pnpm check-licenses   # fails on GPL, AGPL or undeclared licenses
```

- Spanish first: `messages/es.json`, then `messages/en.json`, same keys (tested). The choice
  lives in the `atesta_locale` cookie; the export is prerendered in Spanish.
- Design tokens: `src/styles/tokens.css` is the only file with color, font or radius values
  (tested). Neutral until the owner picks a brand identity.
- Frontend skills: `.claude/skills/frontend-design` and `.claude/skills/react-best-practices`.
