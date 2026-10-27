import { useCallback, useLayoutEffect, useRef, useState, type RefObject } from "react";

export function useStickToBottom(container: RefObject<HTMLElement>, deps: readonly unknown[], paused = false) {
  const following = useRef(true), [atBottom, setAtBottom] = useState(true);
  const scroll = useCallback((smooth = false) => {
    const element = container.current; if (!element) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const options: ScrollToOptions = { top: element.scrollHeight, behavior: smooth && !reduce ? "smooth" : "auto" };
    if (typeof element.scrollTo === "function") element.scrollTo(options); else element.scrollTop = options.top!;
  }, [container]);
  const jump = useCallback(() => { following.current = true; setAtBottom(true); scroll(true); }, [scroll]);
  const onScroll = useCallback(() => {
    const element = container.current; if (!element) return;
    following.current = element.scrollHeight - element.clientHeight - element.scrollTop <= 24;
    setAtBottom(following.current);
  }, [container]);
  useLayoutEffect(() => { if (!paused && following.current) scroll(); }, [scroll, paused, ...deps]);
  return { atBottom, onScroll, jump };
}
