import {render,screen} from "@testing-library/react";
import {describe,expect,it,vi} from "vitest";
import {ChunkCard} from "./chunk-card";
describe("slide chunk card",()=>{
  it("shows audio seconds and no PDF page chips",()=>{
    render(<ChunkCard chunk={{id:"audio-1",text:"Lighthouse fifty two",positions:[],origin:"parsed",enabled:true,audio:{start:0,end:5.38}}} number={1} total={1} selected={false} showPages={false} canChange={false} busy={false} onSelect={vi.fn()} onChip={vi.fn()} onToggle={vi.fn()}/>);
    expect(screen.getByTestId("chunk-audio")).toHaveTextContent("Audio 0.00–5.38 seconds");
    expect(screen.queryByTestId("chunk-page-chip")).toBeNull();
  });
  it("labels the original slide without inventing PDF page chips",()=>{
    render(<ChunkCard chunk={{id:"slide-3",text:"Closing",positions:[],origin:"parsed",enabled:true,slide:{number:3,title:"Closing"}}} number={2} total={3} selected={false} showPages={false} canChange={false} busy={false} onSelect={vi.fn()} onChip={vi.fn()} onToggle={vi.fn()}/>);
    expect(screen.getByTestId("chunk-slide")).toHaveTextContent("Slide 3");
    expect(screen.queryByTestId("chunk-page-chip")).toBeNull();
  });
});
