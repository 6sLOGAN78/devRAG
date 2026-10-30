import {useEffect,useRef,useState} from "react";
import {useQuery,useQueryClient} from "@tanstack/react-query";
import {useTranslation} from "react-i18next";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {Alert} from "@/components/ui/alert";
import {AlertDialog,AlertDialogContent,AlertDialogHeader,AlertDialogTitle,AlertDialogDescription,AlertDialogFooter,AlertDialogCancel,AlertDialogAction} from "@/components/ui/alert-dialog";
import {useCanManageDataset} from "@/hooks/use-dataset-permissions";
import {useUpdateDatasetRequest} from "@/hooks/use-knowledge-request";
import {useWorkspaceStore} from "@/stores/workspace-store";
import {listDatasets,type DatasetDetailView} from "@/services/dataset-service";
import {listDatasetTags,deleteDatasetTags,aggregateDatasetTags,type DatasetTag} from "@/services/dataset-tag-service";
import {ApiError} from "@/services/http";
import {notifySuccess} from "@/services/notify";

function TagList({rows}:{rows:DatasetTag[]}){
  return <ul className="grid gap-2 sm:grid-cols-2">{rows.map(row=><li key={row.tag} className="flex flex-wrap justify-between gap-2 rounded-md border p-3"><span className="break-words">{row.tag}</span><span className="tabular-nums text-muted-foreground">{row.weight.toFixed(3)} · {row.count}</span></li>)}</ul>;
}

export function DatasetTags({dataset}:{dataset:DatasetDetailView}){
  const {t}=useTranslation();
  const tenant=dataset.tenantId;
  const current=useWorkspaceStore(state=>state.activeTenantId)===tenant;
  const canManage=useCanManageDataset(dataset);
  const queryClient=useQueryClient();
  const [open,setOpen]=useState(false);
  const [selected,setSelected]=useState<string[]>([]);
  const [confirm,setConfirm]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [rank,setRank]=useState(String(dataset.pagerank??0));
  const previous=useRef(dataset.pagerank??0);
  const [aggregateOpen,setAggregateOpen]=useState(false);
  const [datasetPage,setDatasetPage]=useState(1);
  const [datasets,setDatasets]=useState<string[]>([dataset.id]);
  const [submitted,setSubmitted]=useState<string[]>([]);
  const inFlight=useRef(false);
  const alive=useRef(true);
  const deleteButton=useRef<HTMLButtonElement>(null);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const update=useUpdateDatasetRequest();
  const tags=useQuery({queryKey:["ws",tenant,"dataset-tags",dataset.id],queryFn:({signal})=>listDatasetTags(dataset.id,signal),retry:false,enabled:current&&open});
  const choices=useQuery({queryKey:["ws",tenant,"tag-datasets",datasetPage],queryFn:()=>listDatasets({tenantId:tenant,page:datasetPage,pageSize:12,keywords:""}),retry:false,enabled:current&&open&&aggregateOpen});
  const aggregation=useQuery({queryKey:["ws",tenant,"dataset-tags","aggregation",submitted],queryFn:({signal})=>aggregateDatasetTags(submitted,signal),retry:false,enabled:current&&open&&aggregateOpen&&submitted.length>0});
  useEffect(()=>{setRank(value=>value===String(previous.current)?String(dataset.pagerank??0):value);previous.current=dataset.pagerank??0;},[dataset.pagerank]);
  useEffect(()=>{if(tags.data)setSelected(values=>values.filter(label=>tags.data.items.some(row=>row.tag===label)));},[tags.data]);
  const isCurrent=()=>alive.current&&useWorkspaceStore.getState().activeTenantId===tenant;
  function failure(value:unknown){
    const data=value instanceof ApiError ? value.data as {reason?:string}|undefined : undefined;
    return t(data?.reason==="parse_running"?"datasets.tags.running":"datasets.tags.failed");
  }
  async function remove(){
    if(inFlight.current||!selected.length||!isCurrent())return;
    inFlight.current=true;setBusy(true);setError(null);
    try{
      await deleteDatasetTags(dataset.id,selected);
      await queryClient.invalidateQueries({queryKey:["ws",tenant,"dataset-tags"]});
      if(isCurrent()){setSelected([]);setConfirm(false);notifySuccess(t("datasets.tags.deleted"));}
    }catch(value){if(isCurrent())setError(failure(value));}
    finally{inFlight.current=false;if(isCurrent())setBusy(false);}
  }
  async function saveRank(){
    if(inFlight.current||!isCurrent())return;
    const value=Number(rank);
    if(!rank.trim()||!Number.isInteger(value)||value<0||value>100){setError(t("datasets.tags.rankInvalid"));return;}
    inFlight.current=true;setBusy(true);setError(null);
    try{await update.mutateAsync({id:dataset.id,tenantId:tenant,changes:{pagerank:value}});if(isCurrent())notifySuccess(t("datasets.tags.rankSaved"));}
    catch(value){if(isCurrent())setError(failure(value));}
    finally{inFlight.current=false;if(isCurrent())setBusy(false);}
  }
  if(!current)return null;
  return <section className="grid gap-4 rounded-lg border bg-card p-4" data-testid="dataset-tags-section">
    <Button type="button" variant="ghost" className="justify-start" data-testid="dataset-tags-open" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>{t("datasets.tags.title")}</Button>
    {open?<div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t("datasets.tags.help")}</p>
      {tags.isPending?<p role="status">{t("datasets.tags.loading")}</p>:null}
      {tags.isError?<Alert role="alert">{t("datasets.tags.failed")} <Button variant="outline" onClick={()=>void tags.refetch()}>{t("datasets.tags.refresh")}</Button></Alert>:null}
      {tags.data?.items.length===0?<p data-testid="dataset-tags-empty">{t("datasets.tags.empty")}</p>:null}
      {tags.data?.items.length?<div role="group" aria-label={t("datasets.tags.selection")} className="grid max-h-80 gap-2 overflow-y-auto sm:grid-cols-2">{tags.data.items.map(row=><label key={row.tag} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-md border p-3"><input type="checkbox" checked={selected.includes(row.tag)} disabled={!canManage||busy||(!selected.includes(row.tag)&&selected.length>=128)} aria-label={row.tag} onChange={event=>setSelected(values=>event.target.checked?[...values,row.tag]:values.filter(value=>value!==row.tag))}/><span className="min-w-0 flex-1 break-words">{row.tag}</span><span className="tabular-nums text-muted-foreground">{row.weight.toFixed(3)} · {t("datasets.tags.chunks",{count:row.count})}</span></label>)}</div>:null}
      {canManage?<>
        <Button ref={deleteButton} type="button" variant="outline" data-testid="tags-delete-selected" disabled={busy||!selected.length} onClick={()=>{setError(null);setConfirm(true);}}>{t("datasets.tags.deleteSelected",{count:selected.length})}</Button>
        <div className="flex flex-wrap items-end gap-3"><label className="grid gap-1 text-sm">{t("datasets.tags.pagerank")}<Input type="number" min={0} max={100} step={1} value={rank} onChange={event=>setRank(event.target.value)} disabled={busy} data-testid="dataset-pagerank"/></label><Button type="button" variant="outline" disabled={busy||rank===String(dataset.pagerank??0)} data-testid="dataset-pagerank-save" onClick={()=>void saveRank()}>{t("datasets.tags.saveRank")}</Button></div>
      </>:null}
      {error?<Alert role="alert">{error}</Alert>:null}
      <Button type="button" variant="outline" data-testid="tags-aggregation-open" aria-expanded={aggregateOpen} onClick={()=>setAggregateOpen(value=>!value)}>{t("datasets.tags.aggregateTitle")}</Button>
      {aggregateOpen?<div className="grid gap-3">
        <p className="text-sm text-muted-foreground">{t("datasets.tags.chooseDatasets")}</p>
        {choices.isPending?<p role="status">{t("datasets.tags.loading")}</p>:null}
        {choices.isError?<Alert role="alert">{t("datasets.tags.failed")} <Button variant="outline" onClick={()=>void choices.refetch()}>{t("datasets.tags.refresh")}</Button></Alert>:null}
        {choices.data?.items.map(item=><label key={item.id} className="flex min-h-11 items-center gap-3"><input type="checkbox" aria-label={item.name} checked={datasets.includes(item.id)} disabled={!datasets.includes(item.id)&&datasets.length>=32} onChange={event=>{setDatasets(values=>event.target.checked?[...values,item.id]:values.filter(value=>value!==item.id));setSubmitted([]);}}/><span className="break-words">{item.name}</span></label>)}
        <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={datasetPage===1} onClick={()=>setDatasetPage(value=>value-1)}>{t("datasets.tags.previous")}</Button><Button variant="outline" disabled={!choices.data||datasetPage*12>=choices.data.total} onClick={()=>setDatasetPage(value=>value+1)}>{t("datasets.tags.next")}</Button><Button data-testid="tags-aggregate" disabled={!datasets.length} onClick={()=>setSubmitted([...datasets].sort())}>{t("datasets.tags.aggregate",{count:datasets.length})}</Button></div>
        {aggregation.isFetching?<p role="status">{t("datasets.tags.loading")}</p>:null}
        {submitted.length>0&&aggregation.isError?<Alert role="alert">{t("datasets.tags.failed")}</Alert>:null}
        {submitted.length>0&&aggregation.data?<div data-testid="tags-aggregate-result"><TagList rows={aggregation.data.items}/>{!aggregation.data.items.length?<p>{t("datasets.tags.empty")}</p>:null}</div>:null}
      </div>:null}
      <AlertDialog open={confirm} onOpenChange={value=>{if(!busy)setConfirm(value);}}><AlertDialogContent data-testid="tags-delete-confirm" onCloseAutoFocus={event=>{event.preventDefault();deleteButton.current?.focus();}} onEscapeKeyDown={event=>{if(busy)event.preventDefault();}}><AlertDialogHeader><AlertDialogTitle>{t("datasets.tags.confirmTitle",{count:selected.length})}</AlertDialogTitle><AlertDialogDescription>{t("datasets.tags.confirmHelp")} {selected.join(", ")}</AlertDialogDescription></AlertDialogHeader>{error?<Alert role="alert">{error}</Alert>:null}<AlertDialogFooter><AlertDialogCancel disabled={busy}>{t("datasets.tags.cancel")}</AlertDialogCancel><AlertDialogAction asChild><Button data-testid="tags-delete-confirm-submit" disabled={busy} onClick={event=>{event.preventDefault();void remove();}}>{busy?t("datasets.tags.deleting"):t("datasets.tags.confirmDelete")}</Button></AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    </div>:null}
  </section>;
}
