import type {AreaHandler, DatasetServer} from "../dataset-server";
import {useUserStore} from "@/stores/user-store";

function visible(server:DatasetServer,id:string){
  const row=server.datasets[id];
  const user=useUserStore.getState().user;
  return row&&user&&(row.permission==="team"||row.created_by===user.id);
}

export const handle:AreaHandler=({server,config,method,url,ok})=>{
  if(url==="/api/v1/datasets/metadata/flattened"&&method==="GET"){
    const ids=String(config.params?.dataset_ids??"").split(",");
    if(ids.some(id=>!visible(server,id)))return ok({fields:[]});
    const fields=new Map<string,{name:string;type:string;values:unknown[]}>();
    for(const id of ids)for(const doc of server.documents[id]??[])for(const [name,value] of Object.entries(doc.metadata??{})){
      const type=Array.isArray(value)?"string_array":value===null?"null":typeof value==="boolean"?"boolean":typeof value==="number"?"number":"string";
      const field=fields.get(name)??{name,type,values:[]};
      if(!field.values.some(existing=>JSON.stringify(existing)===JSON.stringify(value)))field.values.push(value);
      fields.set(name,field);
    }
    const page=Math.max(1,Math.min(100,Number(config.params?.page??1)));
    const all=[...fields.values()].sort((a,b)=>a.name.localeCompare(b.name));
    return ok({fields:all.map(field=>({...field,total:field.values.length,values:field.values.slice((page-1)*100,page*100)})),page,page_size:100,has_more:all.some(field=>field.values.length>page*100)});
  }
  const configMatch=/^\/api\/v1\/datasets\/([^/]+)\/metadata\/config$/.exec(url);
  if(configMatch&&method==="GET")return ok({enabled:false,schema:[],model_id:""});
  const editMatch=/^\/api\/v1\/datasets\/([^/]+)\/documents\/metadatas$/.exec(url);
  if(editMatch&&method==="PATCH"){
    const id=editMatch[1]!;
    const body=JSON.parse(String(config.data)) as {document_ids:string[];metadata:Record<string,string|number|boolean|null|string[]>;mode:string};
    for(const doc of server.documents[id]??[])if(body.document_ids.includes(doc.id))doc.metadata=body.mode==="replace"?body.metadata:{...doc.metadata,...body.metadata};
    return ok({document_ids:body.document_ids,count:body.document_ids.length});
  }
};
