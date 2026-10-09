import * as React from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface PaginationProps extends Omit<React.HTMLAttributes<HTMLElement>, "children"> {
  /** Current page, starting at 1. */
  page: number;
  /** Number of pages. One page or fewer renders nothing. */
  pages: number;
  onPageChange: (page: number) => void;
  previousLabel: string;
  nextLabel: string;
  /** The caption between the buttons, already translated and filled in ("Page 2 of 5"). */
  statusLabel: string;
}

/**
 * Previous and Next with a page caption. The edge buttons are `aria-disabled` rather than `disabled`, so keyboard focus
 * does not jump away when the last page is reached; a click on one does nothing. The caption is a polite live region.
 */
function Pagination({ page, pages, onPageChange, previousLabel, nextLabel, statusLabel, className, ...props }: PaginationProps) {
  if (!Number.isFinite(pages) || pages <= 1) return null;
  const atStart = page <= 1;
  const atEnd = page >= pages;
  return (
    <nav className={cn("flex items-center justify-center gap-4", className)} {...props}>
      <Button type="button" variant="outline" aria-disabled={atStart} className={cn(atStart && "pointer-events-none opacity-50")} onClick={() => !atStart && onPageChange(page - 1)}>
        {previousLabel}
      </Button>
      <span aria-live="polite" className="text-xs font-normal tabular-nums text-muted-foreground">
        {statusLabel}
      </span>
      <Button type="button" variant="outline" aria-disabled={atEnd} className={cn(atEnd && "pointer-events-none opacity-50")} onClick={() => !atEnd && onPageChange(page + 1)}>
        {nextLabel}
      </Button>
    </nav>
  );
}

export { Pagination };
