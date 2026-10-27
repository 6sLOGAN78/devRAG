import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageInput } from "./message-input";

describe("message input", () => {
  const setup = (over: Partial<Parameters<typeof MessageInput>[0]> = {}) => {
    const onSend = vi.fn(), onStop = vi.fn(); const view = render(<MessageInput busy={false} onSend={onSend} onStop={onStop} {...over} />);
    const input = screen.getByRole("textbox", { name: "Message" });
    return { ...view, input, onSend, onStop, type: (value: string) => fireEvent.change(input, { target: { value } }) };
  };
  it("labels and focuses the message field with its hint", () => { const { input } = setup(); expect(input).toHaveFocus(); expect(input).toHaveAccessibleDescription("Enter to send, Shift and Enter for a new line."); });
  it("does not send blank text", () => { const { type, onSend } = setup(); type("  "); const send = screen.getByRole("button", { name: "Send message" }); expect(send).toHaveAttribute("aria-disabled", "true"); fireEvent.click(send); expect(onSend).not.toHaveBeenCalled(); });
  it("sends with Enter and clears the field", async () => { const { type, input, onSend } = setup(); type("Question"); await act(async () => fireEvent.keyDown(input, { key: "Enter" })); expect(onSend).toHaveBeenCalledWith("Question"); expect(input).toHaveValue(""); });
  it("keeps Shift+Enter for a line break", () => { const { type, input, onSend } = setup(); type("Question"); fireEvent.keyDown(input, { key: "Enter", shiftKey: true }); expect(onSend).not.toHaveBeenCalled(); });
  it("does not submit during IME composition", () => { const { type, input, onSend } = setup(); type("问题"); fireEvent.compositionStart(input); fireEvent.keyDown(input, { key: "Enter" }); expect(onSend).not.toHaveBeenCalled(); fireEvent.compositionEnd(input); });
  it("honors the native composing flag", () => { const { type, input, onSend } = setup(); type("问题"); fireEvent.keyDown(input, { key: "Enter", isComposing: true }); expect(onSend).not.toHaveBeenCalled(); });
  it("has no counter below 7000 characters", () => { const { type } = setup(); type("a".repeat(6999)); expect(screen.queryByTestId("chat-counter")).toBeNull(); });
  it("shows the live counter at 7000 characters", () => { const { type } = setup(); type("a".repeat(7000)); expect(screen.getByTestId("chat-counter")).toHaveTextContent("7000/8000"); expect(screen.getByTestId("chat-counter")).toHaveAttribute("aria-live", "polite"); });
  it("blocks sends over 8000 with a visible error", () => { const { type, input, onSend } = setup(); type("a".repeat(8001)); fireEvent.keyDown(input, { key: "Enter" }); expect(screen.getByText("Use 8,000 characters or fewer.")).toBeInTheDocument(); expect(onSend).not.toHaveBeenCalled(); });
  it("keeps a busy textarea readOnly and focusable", () => { const { input } = setup({ busy: true }); expect(input).toHaveAttribute("readonly"); expect(input).not.toBeDisabled(); expect(input).toHaveAttribute("aria-busy", "true"); });
  it("replaces Send with an accessible Stop button", () => { const { onStop } = setup({ busy: true }); expect(screen.queryByRole("button", { name: "Send message" })).toBeNull(); fireEvent.click(screen.getByRole("button", { name: "Stop answer" })); expect(onStop).toHaveBeenCalledOnce(); });
  it("stops on Escape while busy", () => { const { input, onStop } = setup({ busy: true }); fireEvent.keyDown(input, { key: "Escape" }); expect(onStop).toHaveBeenCalledOnce(); });
  it("restores the draft and focus after a refused send", () => {
    const props = { busy: false, onSend: vi.fn(), onStop: vi.fn() }; const view = render(<MessageInput {...props} />); view.rerender(<MessageInput {...props} restoreText="Original draft" />);
    expect(screen.getByRole("textbox")).toHaveValue("Original draft"); expect(screen.getByRole("textbox")).toHaveFocus();
  });
  it("guards a double send before the busy prop arrives", async () => {
    let release = () => {}; const onSend = vi.fn(() => new Promise<void>((resolve) => { release = resolve; })); const { type } = setup({ onSend }); type("Question");
    fireEvent.click(screen.getByRole("button", { name: "Send message" })); fireEvent.click(screen.getByRole("button", { name: "Send message" })); expect(onSend).toHaveBeenCalledOnce(); await act(async () => release());
  });
  it("prevents sends while the assistant is loading", () => { const { type, input, onSend } = setup({ disabled: true }); type("Question"); fireEvent.keyDown(input, { key: "Enter" }); expect(onSend).not.toHaveBeenCalled(); expect(input).not.toBeDisabled(); });
});
