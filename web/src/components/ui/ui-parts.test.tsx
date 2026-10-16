import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Checkbox } from "./checkbox";
import { ChoiceGroup } from "./choice-group";
import { Pagination } from "./pagination";
import { SearchInput } from "./search-input";
import { SegmentedControl } from "./segmented-control";
import { Sheet, SheetContent, SheetTitle } from "./sheet";
import { Switch } from "./switch";
import { Textarea } from "./textarea";

// The parts hold no copy: every label below is what a caller would pass from its own locale keys.

describe("Textarea (UI-10)", () => {
  it("renders a plain textarea with the minimum height and vertical resize only", () => {
    render(<Textarea aria-label="Description" defaultValue="hello" />);
    const field = screen.getByLabelText("Description");
    expect(field.tagName).toBe("TEXTAREA");
    expect(field).toHaveValue("hello");
    expect(field.className).toContain("min-h-20");
    expect(field.className).toContain("resize-y");
  });

  it("forwards its ref and passes native attributes through", () => {
    let node: HTMLTextAreaElement | null = null;
    render(<Textarea ref={(el) => (node = el)} aria-label="Notes" maxLength={10} aria-invalid="true" />);
    expect(node).toBeInstanceOf(HTMLTextAreaElement);
    expect(screen.getByLabelText("Notes")).toHaveAttribute("maxlength", "10");
  });
});

describe("Pagination (UI-10)", () => {
  const labels = { previousLabel: "Previous", nextLabel: "Next" };

  it("shows Previous, Next and the page caption in a polite live region", () => {
    render(<Pagination page={2} pages={5} onPageChange={() => {}} statusLabel="Page 2 of 5" {...labels} />);
    expect(screen.getByRole("button", { name: "Previous" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
    const status = screen.getByText("Page 2 of 5");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status.className).toContain("tabular-nums");
  });

  it("asks for the neighbouring page and nothing else", async () => {
    const onPageChange = vi.fn();
    render(<Pagination page={2} pages={5} onPageChange={onPageChange} statusLabel="Page 2 of 5" {...labels} />);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(onPageChange.mock.calls).toEqual([[3], [1]]);
  });

  it("marks the edge buttons aria-disabled and ignores clicks on them", async () => {
    const onPageChange = vi.fn();
    const { rerender } = render(<Pagination page={1} pages={3} onPageChange={onPageChange} statusLabel="Page 1 of 3" {...labels} />);
    expect(screen.getByRole("button", { name: "Previous" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: "Next" })).not.toHaveAttribute("aria-disabled", "true");
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    rerender(<Pagination page={3} pages={3} onPageChange={onPageChange} statusLabel="Page 3 of 3" {...labels} />);
    expect(screen.getByRole("button", { name: "Next" })).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange).not.toHaveBeenCalled();
  });

  it("renders nothing for one page or none", () => {
    const { container, rerender } = render(<Pagination page={1} pages={1} onPageChange={() => {}} statusLabel="Page 1 of 1" {...labels} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<Pagination page={1} pages={0} onPageChange={() => {}} statusLabel="Page 1 of 0" {...labels} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("SearchInput (UI-10, T-03-23-04)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function setup(onSearch: (value: string) => void, initial = "") {
    return render(<SearchInput value={initial} onSearch={onSearch} label="Search datasets" clearLabel="Clear search" />);
  }

  it("has a label that doubles as the placeholder and a leading icon, and no clear button while empty", () => {
    setup(() => {});
    const input = screen.getByLabelText("Search datasets");
    expect(input).toHaveAttribute("placeholder", "Search datasets");
    expect(input).toHaveAttribute("type", "search");
    expect(screen.getByText("Search datasets", { selector: "label" }).className).toContain("sr-only");
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
  });

  it("calls onSearch once, 300 ms after typing stops", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();
    setup(onSearch);
    const input = screen.getByLabelText("Search datasets");
    fireEvent.change(input, { target: { value: "r" } });
    act(() => vi.advanceTimersByTime(200));
    fireEvent.change(input, { target: { value: "rep" } });
    act(() => vi.advanceTimersByTime(299));
    expect(onSearch).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onSearch).toHaveBeenCalledTimes(1);
    expect(onSearch).toHaveBeenCalledWith("rep");
  });

  it("clears at once through the clear button and focuses the field again", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();
    setup(onSearch);
    const input = screen.getByLabelText("Search datasets");
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(input).toHaveValue("");
    expect(onSearch).toHaveBeenCalledWith("");
    expect(input).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
    // The pending timer of "abc" was cancelled: no stale search follows the clear.
    act(() => vi.advanceTimersByTime(1000));
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it("cancels its timer on unmount so nothing fires afterwards", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();
    const view = setup(onSearch);
    fireEvent.change(screen.getByLabelText("Search datasets"), { target: { value: "late" } });
    view.unmount();
    act(() => vi.advanceTimersByTime(1000));
    expect(onSearch).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("honours a custom debounce and shows an initial value with its clear button", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();
    render(<SearchInput value="start" onSearch={onSearch} label="Find" clearLabel="Clear search" debounceMs={50} />);
    expect(screen.getByLabelText("Find")).toHaveValue("start");
    expect(screen.getByRole("button", { name: "Clear search" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Find"), { target: { value: "starter" } });
    act(() => vi.advanceTimersByTime(50));
    expect(onSearch).toHaveBeenCalledWith("starter");
  });
});

describe("ChoiceGroup (UI-10)", () => {
  const options = [
    { value: "me", title: "Only me", description: "Nobody else sees this dataset." },
    { value: "team", title: "Team", description: "Everyone in the workspace sees it." },
  ];

  function Harness({ onChange }: { onChange?: (value: string) => void }) {
    const [value, setValue] = useState("me");
    return (
      <ChoiceGroup
        legend="Visibility"
        name="permission"
        value={value}
        options={options}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
    );
  }

  it("is a labelled radio group with a title and a description per option", () => {
    render(<Harness />);
    const group = screen.getByRole("group", { name: "Visibility" });
    expect(group.tagName).toBe("FIELDSET");
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.getByRole("radio", { name: /Only me/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Team/ })).not.toBeChecked();
    expect(screen.getByText("Everyone in the workspace sees it.")).toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio")) expect(radio).toHaveAttribute("name", "permission");
  });

  it("selects by click", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: /Team/ }));
    expect(onChange).toHaveBeenCalledWith("team");
    expect(screen.getByRole("radio", { name: /Team/ })).toBeChecked();
  });

  it("moves the selection with the arrow keys", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    screen.getByRole("radio", { name: /Only me/ }).focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(onChange).toHaveBeenLastCalledWith("team");
    expect(screen.getByRole("radio", { name: /Team/ })).toBeChecked();
    await userEvent.keyboard("{ArrowUp}");
    expect(onChange).toHaveBeenLastCalledWith("me");
  });

  it("renders option text as text nodes, never as markup", () => {
    render(
      <ChoiceGroup
        legend="Visibility"
        name="p"
        value="x"
        onChange={() => {}}
        options={[{ value: "x", title: "<b>bold</b>", description: "<img src=x onerror=alert(1)>" }]}
      />,
    );
    expect(screen.getByText("<b>bold</b>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
  });
});

describe("Switch", () => {
  function Harness({ busy = false, disabled = false, onChange }: { busy?: boolean; disabled?: boolean; onChange?: (v: boolean) => void }) {
    const [on, setOn] = useState(false);
    return (
      <Switch
        aria-label="Search"
        checked={on}
        onLabel="On"
        offLabel="Off"
        busy={busy}
        disabled={disabled}
        onChange={(next) => {
          setOn(next);
          onChange?.(next);
        }}
      />
    );
  }

  it("is a native switch showing the current word", async () => {
    render(<Harness />);
    const control = screen.getByRole("switch", { name: "Search" });
    expect(control.tagName).toBe("INPUT");
    expect(control).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("Off")).toBeInTheDocument();
    await userEvent.click(control);
    expect(control).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("On")).toBeInTheDocument();
  });

  it("toggles with Space", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    screen.getByRole("switch").focus();
    await userEvent.keyboard(" ");
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("ignores clicks while busy or disabled and marks busy", async () => {
    const onChange = vi.fn();
    const { unmount } = render(<Harness busy onChange={onChange} />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-busy", "true");
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).not.toHaveBeenCalled();
    unmount();
    render(<Harness disabled onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Checkbox", () => {
  it("sets indeterminate on the DOM node and reports changes", async () => {
    const onChange = vi.fn();
    render(<Checkbox aria-label="Select all" checked={false} indeterminate onChange={onChange} />);
    const box = screen.getByRole("checkbox", { name: "Select all" }) as HTMLInputElement;
    expect(box.indeterminate).toBe(true);
    await userEvent.click(box);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe("SegmentedControl", () => {
  const options = [
    { value: "all", label: "All" },
    { value: "on", label: "On" },
    { value: "off", label: "Off" },
  ] as const;

  function Harness({ onChange }: { onChange?: (v: string) => void }) {
    const [value, setValue] = useState("all");
    return (
      <SegmentedControl
        legend="Filter"
        name="filter"
        value={value}
        options={options}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
    );
  }

  it("is a labelled radio group sharing a name", () => {
    render(<Harness />);
    const group = screen.getByRole("group", { name: "Filter" });
    expect(group.tagName).toBe("FIELDSET");
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    for (const radio of screen.getAllByRole("radio")) expect(radio).toHaveAttribute("name", "filter");
    expect(screen.getByRole("radio", { name: "All" })).toBeChecked();
  });

  it("moves with the arrow keys", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    screen.getByRole("radio", { name: "All" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenLastCalledWith("on");
    expect(screen.getByRole("radio", { name: "On" })).toBeChecked();
  });
});

describe("ChoiceGroup options", () => {
  it("disables an option and points it at its badge", () => {
    render(
      <ChoiceGroup
        legend="Method"
        name="m"
        value="a"
        onChange={() => {}}
        options={[
          { value: "a", title: "Naive", description: "Plain" },
          { value: "b", title: "Paper", description: "Layout", disabled: true, badge: "Later" },
        ]}
      />,
    );
    const radio = screen.getByRole("radio", { name: /Paper/ });
    expect(radio).toBeDisabled();
    const badge = screen.getByText("Later");
    expect(badge.id).not.toBe("");
    expect(radio).toHaveAttribute("aria-describedby", badge.id);
    expect(screen.getByRole("radio", { name: /Naive/ })).not.toHaveAttribute("aria-describedby");
    expect(screen.getByRole("radio", { name: /Naive/ })).not.toBeDisabled();
  });
});

describe("Sheet side", () => {
  it("keeps the left navigation drawer by default", () => {
    render(
      <Sheet open>
        <SheetContent aria-describedby={undefined}>
          <SheetTitle>Menu</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    expect(screen.getByRole("dialog").className).toContain("left-0");
    expect(screen.getByText("Close")).toBeInTheDocument();
  });

  it("draws a right sheet with a caller close label", () => {
    render(
      <Sheet open>
        <SheetContent side="right" closeLabel="Close details" aria-describedby={undefined}>
          <SheetTitle>Details</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toContain("right-0");
    expect(dialog.className).toContain("max-w-xl");
    expect(dialog.className).toContain("slide-in-from-right");
    expect(dialog.className).not.toContain("w-60");
    expect(screen.getByText("Close details")).toBeInTheDocument();
    expect(screen.queryByText("Close")).toBeNull();
  });
});
