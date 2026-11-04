import { useSyncExternalStore } from "react";
import { session } from "../api/client";

/** The current admin session token (or null), re-rendering on sign-in, sign-out and expiry. */
export function useSession(): string | null {
  return useSyncExternalStore(session.subscribe, session.get, () => null);
}
