import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RangeField } from "./range-field";

const props = { id: "weight", label: "Weight", value: 0.3, min: 0, max: 1, step: 0.05, readout: "Vector 30%", onChange: vi.fn() };
describe("native range field", () => {
  it("has a visible associated label", () => { render(<RangeField {...props} />); expect(screen.getByRole("slider", { name: "Weight" })).toBeInTheDocument(); });
  it("exposes the formatted readout to assistive technology", () => { render(<RangeField {...props} />); expect(screen.getByRole("slider")).toHaveAttribute("aria-valuetext", "Vector 30%"); expect(screen.getByText("Vector 30%")).toHaveClass("tabular-nums"); });
  it("applies native min, max and step bounds", () => { render(<RangeField {...props} />); expect(screen.getByRole("slider")).toHaveAttribute("min", "0"); expect(screen.getByRole("slider")).toHaveAttribute("max", "1"); expect(screen.getByRole("slider")).toHaveAttribute("step", "0.05"); });
  it("reports a numeric changed value", () => { const onChange = vi.fn(); render(<RangeField {...props} onChange={onChange} />); fireEvent.change(screen.getByRole("slider"), { target: { value: "0.5" } }); expect(onChange).toHaveBeenCalledWith(0.5); });
  it("connects helper text and renders end labels", () => { render(<RangeField {...props} helper="Meaning share" lowLabel="Low" highLabel="High" />); expect(screen.getByRole("slider")).toHaveAccessibleDescription("Meaning share"); expect(screen.getByText("Low")).toBeInTheDocument(); expect(screen.getByText("High")).toBeInTheDocument(); });
  it("leaves Arrow, Home and End keys to the native range input", () => { render(<RangeField {...props} />); const input = screen.getByRole("slider"); expect(input).toHaveAttribute("type", "range"); for (const key of ["ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"]) expect(fireEvent.keyDown(input, { key, cancelable: true })).toBe(true); });
});
