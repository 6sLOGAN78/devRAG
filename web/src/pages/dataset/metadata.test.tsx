import {act,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect,it} from "vitest";
import {DATASET_ID,documentRow,membershipRow,storedMemberships} from "@/test/dataset-server";
import {OWNER,renderTable,rowOf,server,useFilesServer} from "@/test/files-harness";
import {useWorkspaceStore} from "@/stores/workspace-store";

useFilesServer();
const editUrl=`/api/v1/datasets/${DATASET_ID}/documents/metadatas`;
const flatUrl="/api/v1/datasets/metadata/flattened";

it("opens metadata only on request and merges a selected document field without losing another field",async()=>{
  server.documents[DATASET_ID]=[documentRow(1,{metadata:{subject:"lighthouse",height_metres:52}})];
  renderTable();
  const user=userEvent.setup();
  await screen.findByTestId("documents-table");
  expect(server.callsTo("GET",flatUrl)).toHaveLength(0);
  await user.click(within(rowOf(1)).getByTestId("document-select"));
  await user.click(screen.getByTestId("selection-metadata"));
  expect(await screen.findByTestId("metadata-config")).toHaveTextContent("Automatic metadata off");
  await waitFor(()=>expect(screen.getByText("height_metres")).toBeInTheDocument());
  const editor=screen.getByTestId("metadata-editor");
  await user.type(within(editor).getByLabelText("Field name"),"offset_units");
  await user.selectOptions(within(editor).getByLabelText("Type"),"number");
  await user.type(within(editor).getByLabelText("Value"),"73");
  await user.click(within(editor).getByTestId("metadata-save"));
  await waitFor(()=>expect(server.callsTo("PATCH",editUrl)).toHaveLength(1));
  expect(JSON.parse(String(server.callsTo("PATCH",editUrl)[0]?.data))).toEqual({document_ids:[server.documents[DATASET_ID]![0]!.id],metadata:{offset_units:73},mode:"merge"});
  await waitFor(()=>expect(server.documents[DATASET_ID]![0]!.metadata).toEqual({subject:"lighthouse",height_metres:52,offset_units:73}));
  await waitFor(()=>expect(screen.getByText("offset_units")).toBeInTheDocument());
});

it("blocks invalid keys before a request and hides held old workspace metadata",async()=>{
  server.documents[DATASET_ID]=[documentRow(1,{metadata:{subject:"private-old-value"}})];
  server.memberships.push(membershipRow("t2","Other workspace","normal"));
  act(()=>useWorkspaceStore.getState().initialise(OWNER.id,"t1",storedMemberships(server.memberships)));
  let release:()=>void=()=>{};
  server.holds[`GET ${flatUrl}`]=new Promise<void>(resolve=>{release=resolve;});
  renderTable();
  const user=userEvent.setup();
  await screen.findByTestId("documents-table");
  await user.click(within(rowOf(1)).getByTestId("document-select"));
  await user.click(screen.getByTestId("selection-metadata"));
  const editor=screen.getByTestId("metadata-editor");
  await user.type(within(editor).getByLabelText("Field name"),"a.b");
  await user.click(within(editor).getByTestId("metadata-save"));
  expect(await within(editor).findByRole("alert")).toHaveTextContent("Use a unique field name");
  expect(server.callsTo("PATCH",editUrl)).toHaveLength(0);
  act(()=>useWorkspaceStore.getState().setActive("t2"));
  act(()=>release());
  await waitFor(()=>expect(screen.queryByTestId("dataset-metadata-section")).toBeNull());
  expect(screen.queryByText("private-old-value")).toBeNull();
});
