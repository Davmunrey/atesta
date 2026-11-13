/**
 * The invitation token arrives in the URL fragment, so servers and logs never see it
 * (identity-auth spec). It moves to sessionStorage for the sign-in round trip, is removed from
 * the address bar at once, and is forgotten once the invitation is used.
 */
export const INVITE_KEY = "atesta_invite:v1";

function session(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function captureInviteToken(): string | null {
  const fromUrl = new URLSearchParams(window.location.hash.slice(1)).get("token");
  if (fromUrl) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    try {
      session()?.setItem(INVITE_KEY, fromUrl);
    } catch {
      // Storage disabled: the token still works for this page view.
    }
    return fromUrl;
  }
  try {
    return session()?.getItem(INVITE_KEY) ?? null;
  } catch {
    return null;
  }
}

export function forgetInviteToken(): void {
  try {
    session()?.removeItem(INVITE_KEY);
  } catch {
    // Nothing stored.
  }
}
