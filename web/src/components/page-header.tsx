import type { ReactNode, Ref } from "react";
import { cn } from "@/lib/utils";

/**
 * Page title row. `titleRef` lets a page move focus to the title after an action removes the control that had it (a
 * deleted card); the heading is then focusable by script only (`tabIndex` -1) and shows no focus ring.
 */
export function PageHeader({
  title,
  actions,
  titleRef,
  titleClassName,
  titleHint,
}: {
  title: string;
  actions?: ReactNode;
  titleRef?: Ref<HTMLHeadingElement>;
  /** Extra classes for a long, user-supplied title (clamping, breaking anywhere). */
  titleClassName?: string;
  /** The full title as a tooltip, for a title that may be clamped. */
  titleHint?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <h1
        ref={titleRef}
        title={titleHint}
        tabIndex={titleRef === undefined ? undefined : -1}
        className={cn("min-w-0 break-words text-xl font-semibold leading-tight focus:outline-none", titleClassName)}
      >
        {title}
      </h1>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
