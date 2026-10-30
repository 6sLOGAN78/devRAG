import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { documentsKeyRoot } from "@/hooks/use-document-request";
import { editDocumentMetadata, getMetadataConfig, listFlattenedMetadata, type MetadataValue } from "@/services/document-metadata-service";
import type { DocumentView } from "@/services/document-service";
import { notifySuccess } from "@/services/notify";
import { useWorkspaceStore } from "@/stores/workspace-store";

type ValueType = "string" | "number" | "boolean" | "null" | "string_array";
interface Draft { id: number; key: string; type: ValueType; value: string }
const emptyDraft = (id: number): Draft => ({id, key: "", type: "string", value: ""});
const keyRule = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
const reserved = new Set(["provenance", "source", "generation", "generated", "internal"]);

function valueOf(draft: Draft): MetadataValue {
  if (draft.type === "null") return null;
  if (draft.type === "boolean") {
    if (draft.value !== "true" && draft.value !== "false") throw new Error("value");
    return draft.value === "true";
  }
  if (draft.type === "number") {
    const number = Number(draft.value);
    if (!draft.value.trim() || !Number.isFinite(number)) throw new Error("value");
    return number;
  }
  if (draft.type === "string_array") {
    const values = draft.value.split(",").map(value => value.trim());
    if (values.length > 32 || values.some(value => value.length > 4096)) throw new Error("value");
    return values;
  }
  if (draft.value.length > 4096) throw new Error("value");
  return draft.value;
}

export function DatasetMetadata({datasetId, tenantId, selected, open, onOpenChange}:{datasetId:string;tenantId:string;selected:DocumentView[];open:boolean;onOpenChange:(open:boolean)=>void}) {
  const {t} = useTranslation();
  const client = useQueryClient();
  const current = useWorkspaceStore(state => state.activeTenantId) === tenantId;
  const alive = useRef(true);
  const inFlight = useRef(false);
  const nextId = useRef(1);
  const [drafts, setDrafts] = useState<Draft[]>([emptyDraft(0)]);
  const [errors, setErrors] = useState<Record<number,string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fieldPage,setFieldPage]=useState(1);
  const fields = useQuery({queryKey:["ws",tenantId,"metadata-fields",datasetId,fieldPage],queryFn:({signal})=>listFlattenedMetadata([datasetId],signal,fieldPage),enabled:current&&open,retry:false});
  const config = useQuery({queryKey:["ws",tenantId,"metadata-config",datasetId],queryFn:({signal})=>getMetadataConfig(datasetId,signal),enabled:current&&open,retry:false});
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const isCurrent=()=>alive.current&&useWorkspaceStore.getState().activeTenantId===tenantId;
  const selection=selected.map(item=>item.id);
  function change(id:number,patch:Partial<Draft>){setDrafts(items=>items.map(item=>item.id===id?{...item,...patch}:item));setErrors(old=>{const next={...old};delete next[id];return next;});}
  async function save(){
    if(inFlight.current||!isCurrent()||!selection.length||selected.some(item=>item.run==="1"))return;
    const invalid:Record<number,string>={};
    const metadata:Record<string,MetadataValue>={};
    for(const draft of drafts){
      const key=draft.key.trim().toLowerCase();
      if(!keyRule.test(key)||reserved.has(key)||key.startsWith("internal_")||key.startsWith("generated_")||Object.hasOwn(metadata,key)){invalid[draft.id]=t("datasets.metadata.invalidKey");continue;}
      try{metadata[key]=valueOf(draft);}catch{invalid[draft.id]=t("datasets.metadata.invalidValue");}
    }
    if(Object.keys(invalid).length||!Object.keys(metadata).length){setErrors(invalid);return;}
    if(new TextEncoder().encode(JSON.stringify(metadata)).length>16384){setError(t("datasets.metadata.tooLarge"));return;}
    inFlight.current=true;setBusy(true);setError(null);
    const snapshot=[...selection];
    try{
      await editDocumentMetadata(datasetId,snapshot,metadata,"merge");
      await Promise.all([client.invalidateQueries({queryKey:documentsKeyRoot(tenantId,datasetId)}),client.invalidateQueries({queryKey:["ws",tenantId,"metadata-fields",datasetId]})]);
      if(isCurrent()){setDrafts([emptyDraft(nextId.current++)]);setErrors({});notifySuccess(t("datasets.metadata.saved",{count:snapshot.length}));}
    }catch{if(isCurrent())setError(t("datasets.metadata.failed"));}
    finally{inFlight.current=false;if(isCurrent())setBusy(false);}
  }
  if(!current)return null;
  return <section className="grid gap-4 rounded-lg border bg-card p-4" data-testid="dataset-metadata-section">
    <Button type="button" variant="ghost" className="justify-start" data-testid="dataset-metadata-open" aria-expanded={open} onClick={()=>onOpenChange(!open)}>{t("datasets.metadata.title")}</Button>
    {open?<div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t("datasets.metadata.help")}</p>
      {fields.isPending||config.isPending?<p role="status">{t("datasets.metadata.loading")}</p>:null}
      {fields.isError||config.isError?<Alert role="alert">{t("datasets.metadata.failed")} <Button variant="outline" onClick={()=>{void fields.refetch();void config.refetch();}}>{t("datasets.metadata.retry")}</Button></Alert>:null}
      {config.data?<div data-testid="metadata-config" className="grid gap-1 text-sm"><p>{config.data.enabled?t("datasets.metadata.autoOn"):t("datasets.metadata.autoOff")} · {t("datasets.metadata.schema",{count:config.data.schema.length})}</p>{config.data.modelId?<p className="break-words text-muted-foreground">{t("datasets.metadata.model")}: {config.data.modelId}</p>:null}{config.data.schema.length?<ul className="flex flex-wrap gap-2">{config.data.schema.map(field=><li key={field.name} className="rounded border px-2 py-1">{field.name} ({field.type}){field.required?" *":""}</li>)}</ul>:null}</div>:null}
      {fields.data?.fields.length?<ul className="grid gap-2">{fields.data.fields.map(field=><li key={field.name} className="rounded-md border p-3 text-sm"><strong className="break-words">{field.name}</strong> <span className="text-muted-foreground">({field.type}, {field.total})</span><p className="break-words">{field.values.map(value=>Array.isArray(value)?value.join(", "):value===null?"null":String(value)).join(" · ")}</p></li>)}</ul>:fields.data?<p data-testid="metadata-empty">{t("datasets.metadata.empty")}</p>:null}
      {fields.data?.fields.length?<div className="flex gap-2"><Button type="button" variant="outline" disabled={fieldPage<=1} onClick={()=>setFieldPage(page=>page-1)}>{t("datasets.metadata.previous")}</Button><Button type="button" variant="outline" disabled={!fields.data.hasMore} onClick={()=>setFieldPage(page=>page+1)}>{t("datasets.metadata.next")}</Button></div>:null}
      {selection.length?<div className="grid gap-3 border-t pt-4" data-testid="metadata-editor">
        <p className="text-sm font-medium">{t("datasets.metadata.selected",{count:selection.length})}</p>
        <p className="text-sm text-muted-foreground">{t("datasets.metadata.mergeHelp")}</p>
        {drafts.map(draft=><div key={draft.id} className="grid gap-2 rounded-md border p-3 sm:grid-cols-[1fr_9rem_1fr_auto]">
          <label className="grid gap-1 text-sm">{t("datasets.metadata.field")}<Input data-testid="metadata-key" value={draft.key} disabled={busy} aria-invalid={Boolean(errors[draft.id])} onChange={event=>change(draft.id,{key:event.target.value})}/></label>
          <label className="grid gap-1 text-sm">{t("datasets.metadata.type")}<select data-testid="metadata-type" className="h-10 rounded-md border bg-background px-2" value={draft.type} disabled={busy} onChange={event=>change(draft.id,{type:event.target.value as ValueType,value:""})}>{(["string","number","boolean","null","string_array"] as const).map(type=><option key={type} value={type}>{t(`datasets.metadata.types.${type}`)}</option>)}</select></label>
          <label className="grid gap-1 text-sm">{t("datasets.metadata.value")}<Input data-testid="metadata-value" value={draft.value} disabled={busy||draft.type==="null"} aria-invalid={Boolean(errors[draft.id])} onChange={event=>change(draft.id,{value:event.target.value})}/></label>
          <Button type="button" variant="ghost" disabled={busy||drafts.length===1} onClick={()=>setDrafts(items=>items.filter(item=>item.id!==draft.id))}>{t("datasets.metadata.removeField")}</Button>
          {errors[draft.id]?<p role="alert" className="text-destructive sm:col-span-4">{errors[draft.id]}</p>:null}
        </div>)}
        <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" disabled={busy||drafts.length>=32} onClick={()=>setDrafts(items=>[...items,emptyDraft(nextId.current++)])}>{t("datasets.metadata.addField")}</Button><Button type="button" data-testid="metadata-save" disabled={busy||selected.some(item=>item.run==="1")} onClick={()=>void save()}>{busy?t("datasets.metadata.saving"):t("datasets.metadata.save")}</Button></div>
        {selected.some(item=>item.run==="1")?<p role="status">{t("datasets.metadata.parsing")}</p>:null}
        {error?<Alert role="alert">{error}</Alert>:null}
      </div>:null}
    </div>:null}
  </section>;
}
