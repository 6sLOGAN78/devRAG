import {describe,expect,it} from "vitest";
import {slideOf} from "./slide-features";
import {toChunk} from "./chunk-service";
import {toSourceHit} from "./chat-service";
describe("slide evidence",()=>{
  it("maps only bounded typed identity into chunk and hit views",()=>{
    const slide={number:4,title:"<b>Original title</b>"};
    expect(toChunk({slide}).slide).toEqual(slide);
    expect(toSourceHit({slide}).slide).toEqual(slide);
    for(const raw of [{number:0,title:"x"},{number:20001,title:"x"},{number:2.1,title:"x"},{number:"2",title:"x"},{number:2,title:"x".repeat(1025)},null]) expect(slideOf(raw)).toBeUndefined();
  });
});
