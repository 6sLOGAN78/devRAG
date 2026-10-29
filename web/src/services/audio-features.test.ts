import { describe, expect, it } from "vitest";
import { audioOf } from "./audio-features";
import { toChunk } from "./chunk-service";
import { toSourceHit } from "./chat-service";
import { sourceFromHit } from "@/components/source-drawer/source-model";

describe("audio timestamp evidence", () => {
  it("keeps seconds in chunk, retrieval and source views", () => {
    const audio={start:1.25,end:5.38};
    expect(toChunk({audio}).audio).toEqual(audio);
    const hit=toSourceHit({audio,doc_name:"speech.mp3",positions:[]});
    expect(sourceFromHit(hit,1).audio).toEqual(audio);
    expect(hit.positions).toEqual([]);
    for(const value of [null,{start:NaN,end:2},{start:-1,end:2},{start:3,end:2},{start:0,end:61},{start:"1",end:2}]) expect(audioOf(value)).toBeUndefined();
  });
});
