import type { ReactNode, Ref } from "react";

/**
 * Page title row. `titleRef` lets a page move focus to the title after an action removes the control that had it (a
 * deleted card); the heading is then focusable by script only (`tabIndex` -1) and shows no focus ring.
 */
export function PageHeader({ title, actions, titleRef }: { title: string; actions?: ReactNode; titleRef?: Ref<HTMLHeadingElement> }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <h1 ref={titleRef} tabIndex={titleRef === undefined ? undefined : -1} className="min-w-0 break-words text-xl font-semibold leading-tight focus:outline-none">
        {title}
      </h1>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
