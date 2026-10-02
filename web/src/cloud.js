import {createClient} from '@supabase/supabase-js';
import {jobs,putJob,compactJob} from './outbox.js';
export const CLOUD_CONFIG={url:'https://muhxebuwucyknvdmdzsh.supabase.co',key:'sb_publishable_xehZtaB1RXWgx--G0HlLrw_snF6Iik7'};
export const cloud=createClient(CLOUD_CONFIG.url,CLOUD_CONFIG.key);
export let session=null;
export async function initCloud(onChange){session=(await cloud.auth.getSession()).data.session;cloud.auth.onAuthStateChange((_event,s)=>{session=s;onChange();});}
export async function api(action,body={}){
  const {data:{session:s},error}=await cloud.auth.getSession();if(error||!s)throw Error('수집 계정 로그인이 필요합니다.');
  const {data,error:err}=await cloud.functions.invoke('collect',{body:{action,...body}});
  if(err){let detail;try{detail=await err.context?.json();}catch{}const e=Error(detail?.error||err.message);e.status=err.context?.status;e.permanent=[400,403,409,413,422].includes(e.status);throw e;}return data;
}
let pumping=false;
export async function pump(onChange=()=>{}){
  if(pumping||!session||!navigator.onLine)return;pumping=true;
  try{for(const job of await jobs()){
    if(job.owner_id!==session.user.id||job.state!=='pending'||(job.next||0)>Date.now())continue;
    try{
      if(job.action==='withdraw'){await api('withdraw',{client_record_id:job.id});await compactJob({...job,state:'complete'});continue;}
      const opened=await api('begin',{payload:job.payload});
      if(opened.status!=='complete'){
        for(const im of job.payload.images){const signed=opened.uploads.find(x=>x.kind===im.kind);const {error}=await cloud.storage.from('raid-evidence').uploadToSignedUrl(signed.path,signed.token,job.blobs[im.kind],{contentType:im.mime});if(error&&!['409','400'].includes(String(error.statusCode)))throw error; /* Existing immutable file is checked by finalize hash. */}
        await api('finalize',{client_record_id:job.id});
      }
      // Read current row to respect deletion that occurred during uploads.
      const current=(await jobs()).find(j=>j.id===job.id);if(current?.action==='withdraw'){await api('withdraw',{client_record_id:job.id});await compactJob(current);}else await compactJob(job);
    }catch(e){const current=(await jobs()).find(j=>j.id===job.id);if(current?.action==='withdraw'&&job.action!=='withdraw')continue;await putJob({...job,state:e.permanent?'failed':'pending',attempts:(job.attempts||0)+1,error:e.message,next:Date.now()+Math.min(300000,5000*2**Math.min(job.attempts||0,6))});}
    onChange();
  }}finally{pumping=false;onChange();}
}
