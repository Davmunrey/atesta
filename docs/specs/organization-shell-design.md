# Spec: Organization shell design and navigation

- Status: approved scope from owner request, 2026-11-13 (continue independently, review design
  and style, keep the local preview updated).
- Builds on: web-shell; landing-legal decisions L4 and L5.
- Independent of: scanner ingestion, connectors and recorded product views.

## Problem

The working identity screens still use neutral system fonts and a weak hierarchy. Organization
navigation exists only on the overview, so members and invitations become dead ends. Long
organization names, email addresses and tables also need a usable narrow-screen layout.

## Acceptance criteria

- Use the approved paper/ink/yellow identity through semantic tokens. Keep a coherent dark
  app theme; public routes remain light regardless of the system preference.
- Self-host Newsreader (display), IBM Plex Sans (interface) and IBM Plex Mono (invitation links),
  retaining their licenses and exact source versions. No third-party font requests.
- The product name comes from `brand.name` in both locales.
- Organization overview, members and invitations share persistent navigation and an
  organization selector. Mark the current page; expose invitations only to owners/admins.
- Switching organizations preserves the current section when permitted. Switching to a member
  organization while viewing invitations returns to its overview. Invalid or missing organization
  IDs never expose organization navigation or select another organization implicitly.
- Organization lists and overview actions have clear hierarchy without fabricated metrics.
  Tables scroll within a named, keyboard-focusable region when needed; the page itself does not
  overflow at 375, 768 or 1280 CSS pixels, including long names and email addresses.
- Controls have visible hover, keyboard focus and disabled states. Motion is limited to short
  interaction transitions and is suppressed with reduced motion.
- Verify all existing behavior, contrast pairs, responsive navigation, local font loading and
  the strict CSP. Preserve ES/EN parity. No backend or permission changes.

## Verification

Unit tests exercise the real layout with synthetic API replies: current links, role restrictions,
unknown organization IDs and organization switching. Browser checks use the local API and a
synthetic organization at mobile/tablet/desktop widths, both themes and reduced motion. Run
the existing full suites, static build, CSP and license checks, recording runtime evidence with REA.
