# Demo organization

For sales demos and pilot sessions on the local stack, never on a hosted environment.

1. Start the local stack: fake Cognito on :9000, the API on :8000 with
   `ATESTA_CATALOG_INCLUDE_DRAFTS=true`, and the web on :3000. Import the preview catalog.
2. Run `npx -y node@22 scripts/demo-seed.ts` from `apps/web`.

   It signs in as `demo.responsable@example.test` (code `123456`) and builds the demo through the
   public API only. It creates:
   - ENS scope and 40 assessed measures;
   - the security officer review;
   - three policies, two of them approved;
   - a closed access review;
   - a closed training with three confirmations;
   - an incident with a note;
   - an API token with the scope `evidence:write` that has sent one evidence statement.
3. The script prints the link. The content lives in `scripts/demo/es.json`: change names there, not
   in the script.

The script refuses any base URL that is not `localhost` or `127.0.0.1`. Each run creates a new
organization.
