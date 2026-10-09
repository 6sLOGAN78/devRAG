import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Progress } from "./progress";

describe("Progress (UI-12)", () => {
  it("is a determinate progressbar with its range, value and label", () => {
    render(<Progress value={42} label="Upload progress for a.pdf" />);
    const bar = screen.getByRole("progressbar", { name: "Upload progress for a.pdf" });
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(bar).not.toHaveAttribute("aria-valuetext");
  });

  it("draws the fill at the value and keeps the track 8 px high", () => {
    render(<Progress value={42} label="x" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.className).toContain("h-2");
    expect(bar.className).toContain("bg-border");
    const fill = bar.firstElementChild as HTMLElement;
    expect(fill.style.width).toBe("42%");
    expect(fill.className).toContain("bg-primary");
  });

  it("clamps a value outside 0 to 100 and treats NaN as 0", () => {
    const { rerender } = render(<Progress value={150} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    rerender(<Progress value={-5} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    rerender(<Progress value={Number.NaN} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });

  it("carries a value text when given (the Finishing state)", () => {
    render(<Progress value={100} label="x" valueText="Finishing" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Finishing");
  });

  it("turns the width transition off under reduced motion", () => {
    render(<Progress value={10} label="x" />);
    const fill = screen.getByRole("progressbar").firstElementChild as HTMLElement;
    expect(fill.className).toContain("transition-[width]");
    expect(fill.className).toContain("motion-reduce:transition-none");
  });
});
