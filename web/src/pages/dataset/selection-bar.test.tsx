import {render,screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {SelectionBar} from "./selection-bar";

it("opens the selected metadata action and blocks it while a bulk operation is busy",async()=>{
  const open=vi.fn();
  const props={count:2,parseCount:2,cancelCount:0,busy:false,onParse:vi.fn(),onCancel:vi.fn(),onClear:vi.fn(),onMetadata:open};
  const {rerender}=render(<SelectionBar {...props}/>);
  const user=userEvent.setup();
  await user.click(screen.getByTestId("selection-metadata"));
  expect(open).toHaveBeenCalledTimes(1);
  rerender(<SelectionBar {...props} busy/>);
  expect(screen.getByTestId("selection-metadata")).toHaveAttribute("aria-disabled","true");
  await user.click(screen.getByTestId("selection-metadata"));
  expect(open).toHaveBeenCalledTimes(1);
});
