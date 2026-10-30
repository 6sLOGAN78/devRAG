import {datasetPath,datasetsPath} from "@/constants/api-paths";
import {asRecord,count,text} from "./mapping";
import {request} from "./http";
export interface DatasetTag {tag:string;weight:number;count:number}
export interface TagPage {items:DatasetTag[];total:number}
function page(raw:unknown):TagPage {
  const dto=asRecord(raw);
  const items=Array.isArray(dto.items)?dto.items.flatMap(value=>{
    const row=asRecord(value);
    const tag=text(row.tag);
    return tag&&tag.length<=64&&typeof row.weight==="number"&&Number.isFinite(row.weight)&&row.weight>=0&&row.weight<=1 ? [{tag,weight:row.weight,count:count(row.count)}] : [];
  }):[];
  return {items,total:count(dto.total)};
}
export async function listDatasetTags(id:string,signal?:AbortSignal):Promise<TagPage>{
  return page(await request<unknown>({url:`${datasetPath(id)}/tags`,method:"GET",signal,timeout:65000},{silent:true}));
}
export async function aggregateDatasetTags(ids:string[],signal?:AbortSignal):Promise<TagPage>{
  return page(await request<unknown>({url:`${datasetsPath}/tags/aggregation`,method:"GET",params:{dataset_ids:ids.join(",")},signal,timeout:65000},{silent:true}));
}
export async function deleteDatasetTags(id:string,tags:string[]):Promise<void>{
  await request({url:`${datasetPath(id)}/tags`,method:"DELETE",data:{tags},timeout:65000},{silent:true});
}
