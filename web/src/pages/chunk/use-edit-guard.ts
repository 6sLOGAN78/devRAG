import { useCallback, useEffect, useRef, useState } from "react";
import { useBlocker, type BlockerFunction } from "react-router";

export interface EditGuard {
  /** Runs `action` now when nothing is changed, otherwise holds it and opens the Discard dialog. */
  guard: (action: () => void) => void;
  /** The Discard dialog is open: an action or a route change is held back. */
  pending: boolean;
  /** Discard: lets the held action or route change through. */
  confirm: () => void;
  /** Keep editing: drops the held action. */
  cancel: () => void;
  /** The text was saved or discarded: from now on nothing is held, even before the next render. */
  release: () => void;
}

/** The part of the address that says which document the page shows. Searching, filtering and paging are guarded as actions. */
function documentOf(search: string): string {
  const params = new URLSearchParams(search);
  return `${params.get("id") ?? ""}:${params.get("doc") ?? ""}`;
}

/**
 * Keeps typed text from being lost silently (UI-SPEC Unsaved changes). While `dirty`, an action passed to `guard` is held
 * until the user decides, a navigation to another route or document is held by the router's blocker, and reload or tab
 * close asks the browser to confirm. Nothing else is unsaved state: the typed text is the only thing guarded.
 */
export function useEditGuard(dirty: boolean): EditGuard {
  const live = useRef(dirty);
  const [held, setHeld] = useState<(() => void) | null>(null);

  useEffect(() => {
    live.current = dirty;
  }, [dirty]);

  const shouldBlock: BlockerFunction = useCallback(
    ({ currentLocation, nextLocation }) => live.current && (currentLocation.pathname !== nextLocation.pathname || documentOf(currentLocation.search) !== documentOf(nextLocation.search)),
    [],
  );
  const blocker = useBlocker(shouldBlock);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const guard = useCallback((action: () => void) => {
    if (!live.current) action();
    else setHeld(() => action);
  }, []);

  const release = useCallback(() => {
    live.current = false;
  }, []);

  const confirm = useCallback(() => {
    live.current = false;
    if (blocker.state === "blocked") blocker.proceed();
    if (held !== null) {
      setHeld(null);
      held();
    }
  }, [blocker, held]);

  const cancel = useCallback(() => {
    if (blocker.state === "blocked") blocker.reset();
    setHeld(null);
  }, [blocker]);

  return { guard, pending: held !== null || blocker.state === "blocked", confirm, cancel, release };
}
