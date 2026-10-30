import type {AreaHandler,DatasetServer} from "../dataset-server";
import {useUserStore} from "@/stores/user-store";
export interface TagRow {tag:string;weight:number;count:number}
const state=(server:DatasetServer)=>server.areaState<Record<string,TagRow[]>>("tags",()=>({}));
export function setTags(server:DatasetServer,id:string,rows:TagRow[]){state(server)[id]=rows;}
export const handle:AreaHandler=({server,config,method,url,ok})=>{
  if(url==="/api/v1/datasets"&&method==="GET"){
    const tenant=String(config.params?.tenant_id??"");
    const keywords=String(config.params?.keywords??"").toLowerCase();
    const page=Math.max(1,Number(config.params?.page??1));
    const size=Math.max(1,Number(config.params?.page_size??12));
    const userId=useUserStore.getState().user?.id;
    const rows=Object.values(server.datasets).filter(row=>row.tenant_id===tenant&&(row.permission==="team"||row.created_by===userId)&&row.name.toLowerCase().includes(keywords));
    return ok({items:rows.slice((page-1)*size,page*size),total:rows.length});
  }
  if(url==="/api/v1/datasets/tags/aggregation"&&method==="GET"){
    const ids=String(config.params?.dataset_ids??"").split(",");
    const rows=ids.flatMap(id=>state(server)[id]??[]);
    return ok({items:rows,total:rows.length});
  }
  const match=/^\/api\/v1\/datasets\/([^/]+)\/tags$/.exec(url);
  if(!match)return;
  const id=match[1]!;
  if(method==="GET"){const rows=state(server)[id]??[];return ok({items:rows,total:rows.length});}
  if(method==="DELETE"){
    const tags=JSON.parse(String(config.data)).tags as string[];
    const before=state(server)[id]??[];
    state(server)[id]=before.filter(row=>!tags.includes(row.tag));
    return ok({deleted:before.filter(row=>tags.includes(row.tag)).map(row=>row.tag),count:before.length-state(server)[id]!.length});
  }
};
