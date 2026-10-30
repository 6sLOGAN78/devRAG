import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {act,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {MemoryRouter} from "react-router";
import {it,expect} from "vitest";
import {DatasetWorkspace} from "./dataset-workspace";
import {getDataset} from "@/services/dataset-service";
import {registerQueryClient} from "@/services/http";
import {DATASET_ID,datasetRow} from "@/test/dataset-server";
import {OWNER,actAs,server,useFilesServer} from "@/test/files-harness";
import {setTags} from "@/test/server-areas/tags";
import {useWorkspaceStore} from "@/stores/workspace-store";
useFilesServer();

async function mount(){
  const dataset=await getDataset(DATASET_ID);
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
  registerQueryClient(client);
  render(<QueryClientProvider client={client}><MemoryRouter><DatasetWorkspace dataset={dataset} ready onDeleted={()=>{}} onDeleteDialogChange={()=>{}}/></MemoryRouter></QueryClientProvider>);
  return userEvent.setup();
}

it("loads tags only on opening and deletes only an explicit confirmed selection",async()=>{
  setTags(server,DATASET_ID,[{tag:"lighthouse",weight:.6,count:1}]);
  const user=await mount();
  expect(await screen.findByTestId("dataset-tags-open")).toHaveTextContent("Tags");
  expect(server.callsTo("GET",`/api/v1/datasets/${DATASET_ID}/tags`)).toHaveLength(0);
  await user.click(screen.getByTestId("dataset-tags-open"));
  await screen.findByRole("checkbox",{name:"lighthouse"});
  await user.click(screen.getByRole("checkbox",{name:"lighthouse"}));
  expect(server.callsTo("DELETE",`/api/v1/datasets/${DATASET_ID}/tags`)).toHaveLength(0);
  await user.click(screen.getByTestId("tags-delete-selected"));
  const dialog=await screen.findByTestId("tags-delete-confirm");
  expect(within(dialog).getByText(/lighthouse/)).toBeInTheDocument();
  await user.click(within(dialog).getByTestId("tags-delete-confirm-submit"));
  await waitFor(()=>expect(server.callsTo("DELETE",`/api/v1/datasets/${DATASET_ID}/tags`)).toHaveLength(1));
  await waitFor(()=>expect(screen.getByTestId("dataset-tags-empty")).toBeInTheDocument());
  expect(JSON.parse(String(server.callsTo("DELETE",`/api/v1/datasets/${DATASET_ID}/tags`)[0]?.data))).toEqual({tags:["lighthouse"]});
});

it("saves an integer PageRank and aggregates only explicitly selected datasets",async()=>{
  setTags(server,DATASET_ID,[{tag:"lighthouse",weight:.6,count:1}]);
  server.datasets["ds-2"]=datasetRow({id:"ds-2",name:"Other dataset"});
  setTags(server,"ds-2",[{tag:"calibration",weight:1,count:1}]);
  const user=await mount();
  await user.click(await screen.findByTestId("dataset-tags-open"));
  await screen.findByRole("checkbox",{name:"lighthouse"});
  const rank=screen.getByTestId("dataset-pagerank");
  await user.clear(rank);
  await user.type(rank,"101");
  await user.click(screen.getByTestId("dataset-pagerank-save"));
  expect(server.callsTo("PUT",`/api/v1/datasets/${DATASET_ID}`)).toHaveLength(0);
  await user.clear(rank);
  await user.type(rank,"2");
  await user.click(screen.getByTestId("dataset-pagerank-save"));
  await waitFor(()=>expect(server.callsTo("PUT",`/api/v1/datasets/${DATASET_ID}`)).toHaveLength(1));
  expect(JSON.parse(String(server.callsTo("PUT",`/api/v1/datasets/${DATASET_ID}`)[0]?.data))).toEqual({pagerank:2});
  await user.click(screen.getByTestId("tags-aggregation-open"));
  await screen.findByRole("checkbox",{name:"Other dataset"});
  await user.click(screen.getByTestId("tags-aggregate"));
  await screen.findByTestId("tags-aggregate-result");
  expect(server.callsTo("GET","/api/v1/datasets/tags/aggregation")[0]?.params).toEqual({dataset_ids:DATASET_ID});
  await user.click(screen.getByRole("checkbox",{name:"Other dataset"}));
  await user.click(screen.getByTestId("tags-aggregate"));
  await waitFor(()=>expect(server.callsTo("GET","/api/v1/datasets/tags/aggregation")).toHaveLength(2));
  expect(server.callsTo("GET","/api/v1/datasets/tags/aggregation")[1]?.params).toEqual({dataset_ids:["ds-2",DATASET_ID].sort().join(",")});
});

it("hides management for a reader and never shows a held old-workspace tag response",async()=>{
  actAs({...OWNER,id:"u9",tenantId:"t2",tenantName:"Other workspace"},"normal");
  setTags(server,DATASET_ID,[{tag:"private-old-tag",weight:1,count:1}]);
  let release:()=>void=()=>{};
  server.holds[`GET /api/v1/datasets/${DATASET_ID}/tags`]=new Promise<void>(resolve=>{release=resolve;});
  const user=await mount();
  await user.click(await screen.findByTestId("dataset-tags-open"));
  expect(screen.queryByTestId("tags-delete-selected")).toBeNull();
  expect(screen.queryByTestId("dataset-pagerank-save")).toBeNull();
  act(()=>useWorkspaceStore.getState().setActive("t2"));
  act(()=>release());
  await waitFor(()=>expect(screen.queryByTestId("dataset-tags-section")).toBeNull());
  expect(screen.queryByText("private-old-tag")).toBeNull();
});
