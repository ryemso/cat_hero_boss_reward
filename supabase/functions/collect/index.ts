import {createClient} from 'npm:@supabase/supabase-js@2.57.4';
const url=Deno.env.get('SUPABASE_URL')!,secret=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const db=createClient(url,secret,{auth:{persistSession:false,autoRefreshToken:false}});
const ORIGINS=['https://ryemso.github.io','http://localhost:5173','http://127.0.0.1:5173','http://localhost:4173','http://127.0.0.1:4173'];
const keys=new Set(['blue_item','green_item','white_item','legend_pickup','companion_summon','rune_summon','random_rune','purple_recipe','blue_recipe','green_recipe','red_recipe_excluded','purple_item_excluded']);
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i,hash=/^[a-f0-9]{64}$/;
class Problem extends Error{constructor(public status:number,message:string){super(message);}}
function assert(v:unknown,message:string,status=400):asserts v{if(!v)throw new Problem(status,message);}
function check(result:any){if(result.error)throw new Problem(500,'서버 저장 오류');return result.data;}
const digest=async(b:ArrayBuffer|string)=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',typeof b==='string'?new TextEncoder().encode(b):b))].map(n=>n.toString(16).padStart(2,'0')).join('');
function cleanPayload(p:any){
  assert(p&&p.version===1&&uuid.test(p.client_record_id),'지원하지 않는 제출 형식');
  assert(typeof p.boss==='string'&&p.boss.length>0&&p.boss.length<=80,'보스 이름 오류');
  assert(/^\d{4}-\d{2}-\d{2}$/.test(p.date)&&Number.isFinite(Date.parse(p.date))&&/^([01]\d|2[0-3]):[0-5]\d$/.test(p.time),'날짜/시간 오류');
  assert(Number.isInteger(p.participant_count)&&p.participant_count>0&&p.participant_count<=200,'참여 인원 오류');
  assert(p.notice_version==='2026-10-02-v1'&&p.mapping_version==='U01-U33-v1','수집 안내/매핑 버전 오류');
  assert(typeof p.timezone==='string'&&p.timezone.length<=80,'시간대 오류');
  assert(p.canvas&&Number.isInteger(p.canvas.width)&&Number.isInteger(p.canvas.height)&&p.canvas.width>0&&p.canvas.height>0&&p.canvas.width*p.canvas.height<=40000000,'이미지 해상도 제한');
  assert(Array.isArray(p.images)&&p.images.length===2&&new Set(p.images.map((i:any)=>i.kind)).size===2,'원본/마킹 이미지 필요');
  const images=p.images.map((i:any)=>{assert(['original','annotated'].includes(i.kind)&&hash.test(i.sha256)&&['image/png','image/jpeg'].includes(i.mime)&&Number.isInteger(i.bytes)&&i.bytes>0&&i.bytes<=20971520,'이미지 형식/크기 오류');return {kind:i.kind,sha256:i.sha256,mime:i.mime,bytes:i.bytes};}).sort((a:any,b:any)=>a.kind.localeCompare(b.kind));
  assert(Array.isArray(p.rewards)&&p.rewards.length>0&&p.rewards.length<=100,'보상 개수 오류');
  const num=(v:any)=>v===null||Number.isFinite(v)&&v>=0&&v<=1;
  const rewards=p.rewards.map((r:any,n:number)=>{
    assert(keys.has(r.reward_key)&&Number.isInteger(r.quantity)&&r.quantity>=0&&r.quantity<=100000000,'보상/수량 오류');
    assert(r.candidate_id===null||/^U(0[1-9]|[12]\d|3[0-3])$/.test(r.candidate_id),'후보ID 오류');
    assert(num(r.score)&&num(r.quantity_confidence)&&(r.ocr_quantity===null||Number.isInteger(r.ocr_quantity)&&r.ocr_quantity>=0),'인식값 오류');
    const b=r.box;assert(b===null||b&&['x','y','w','h'].every(k=>Number.isFinite(b[k])&&b[k]>=0&&b[k]<=1)&&b.w>0&&b.h>0&&b.x+b.w<=1.001&&b.y+b.h<=1.001,'마킹 좌표 오류');
    assert(r.recognized_reward_key===null||keys.has(r.recognized_reward_key),'인식 보상 오류');
    return {row_number:n,reward_key:r.reward_key,quantity:r.quantity,candidate_id:r.candidate_id,score:r.score,ocr_quantity:r.ocr_quantity,quantity_confidence:r.quantity_confidence,rarity:typeof r.rarity==='string'?r.rarity.slice(0,15):null,box:b?{x:b.x,y:b.y,w:b.w,h:b.h}:null,recognized_reward_key:r.recognized_reward_key,reward_corrected:!!r.reward_corrected,quantity_corrected:!!r.quantity_corrected};
  });
  return {version:1,client_record_id:p.client_record_id,boss:p.boss,date:p.date,time:p.time,timezone:p.timezone,participant_count:p.participant_count,notice_version:p.notice_version,mapping_version:p.mapping_version,recognition_version:'lab-cosine-v1',canvas:{width:p.canvas.width,height:p.canvas.height},images,rewards};
}
function dimensions(bytes:Uint8Array,mime:string){
  const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(mime==='image/png'){
    assert(bytes.length>=24&&[137,80,78,71,13,10,26,10].every((x,i)=>bytes[i]===x),'PNG 데이터 오류',422);
    return {width:v.getUint32(16),height:v.getUint32(20)};
  }
  assert(bytes.length>4&&bytes[0]===255&&bytes[1]===216,'JPEG 데이터 오류',422);
  for(let i=2;i<bytes.length-8;){if(bytes[i]!==255){i++;continue;}const marker=bytes[i+1];if(marker===255){i++;continue;}if(marker===217||marker===218)break;const length=v.getUint16(i+2);assert(length>=2&&i+2+length<=bytes.length,'JPEG 형식 오류',422);if([192,193,194,195,197,198,199,201,202,203,205,206,207].includes(marker))return {width:v.getUint16(i+7),height:v.getUint16(i+5)};i+=2+length;}
  throw new Problem(422,'JPEG 해상도 확인 실패');
}
const path=(s:any,i:any)=>`${s.owner_id}/${s.client_record_id}/${i.kind}.${i.mime==='image/png'?'png':'jpg'}`;
Deno.serve(async(req)=>{
  const origin=req.headers.get('origin'),cors={'Access-Control-Allow-Origin':origin&&ORIGINS.includes(origin)?origin:ORIGINS[0],'Access-Control-Allow-Headers':'authorization, x-client-info, apikey, content-type','Access-Control-Allow-Methods':'POST, OPTIONS','Vary':'Origin'};
  const respond=(data:any,status=200)=>new Response(JSON.stringify(data),{status,headers:{...cors,'Content-Type':'application/json'}});
  if(req.method==='OPTIONS')return new Response('ok',{headers:cors});
  try{
    assert(req.method==='POST','POST만 허용',405);assert(!origin||ORIGINS.includes(origin),'허용하지 않는 출처',403);
    const token=req.headers.get('authorization')?.replace(/^Bearer\s+/i,'');assert(token,'로그인 필요',401);
    const auth=await db.auth.getUser(token);assert(!auth.error&&auth.data.user&&!auth.data.user.is_anonymous,'로그인 필요',401);const user=auth.data.user;
    const text=await req.text();assert(text.length<=100000,'제출 내용이 너무 큽니다',413);const body=JSON.parse(text);
    const admin=!!check(await db.from('admin_members').select('user_id').eq('user_id',user.id).maybeSingle());
    if(body.action==='identity')return respond({user_id:user.id,admin});
    if(body.action==='begin'){
      const p=cleanPayload(body.payload),h=await digest(JSON.stringify(p));
      let s=check(await db.from('submissions').select('*').eq('owner_id',user.id).eq('client_record_id',p.client_record_id).maybeSingle());
      if(!s){const {count,error}=await db.from('submissions').select('id',{count:'exact',head:true}).eq('owner_id',user.id).gte('created_at',new Date(Date.now()-86400000).toISOString());assert(!error&&count!<100,'하루 제출 제한에 도달했습니다',429);
        const inserted=await db.from('submissions').insert({owner_id:user.id,client_record_id:p.client_record_id,payload_hash:h,payload:p,original_hash:p.images.find((i:any)=>i.kind==='original').sha256}).select('*').single();
        if(inserted.error?.code==='23505')s=check(await db.from('submissions').select('*').eq('owner_id',user.id).eq('client_record_id',p.client_record_id).single());else s=check(inserted);
      }
      assert(s.payload_hash===h,'같은 기록ID에 다른 내용이 있습니다',409);assert(s.status!=='withdrawn','철회된 기록입니다',409);
      if(s.status==='complete')return respond({status:'complete',id:s.id});
      const uploads=[];for(const i of p.images){const objectPath=path(s,i),signed=check(await db.storage.from('raid-evidence').createSignedUploadUrl(objectPath));uploads.push({kind:i.kind,path:objectPath,token:signed.token});}return respond({id:s.id,status:s.status,uploads});
    }
    if(['finalize','status','withdraw'].includes(body.action)){
      assert(uuid.test(body.client_record_id),'기록ID 오류');const s=check(await db.from('submissions').select('*').eq('owner_id',user.id).eq('client_record_id',body.client_record_id).maybeSingle());
      if(!s&&body.action==='withdraw')return respond({status:'withdrawn'});assert(s,'기록을 찾을 수 없습니다',404);
      if(body.action==='status')return respond({status:s.status,review_status:s.review_status});
      if(body.action==='withdraw'){check(await db.from('submissions').update({status:'withdrawn'}).eq('id',s.id).eq('owner_id',user.id));return respond({status:'withdrawn'});}
      assert(s.status!=='withdrawn','철회된 기록입니다',409);if(s.status==='complete')return respond({status:'complete'});
      const images=[];for(const i of s.payload.images){const object_path=path(s,i),blob=check(await db.storage.from('raid-evidence').download(object_path));assert(blob.size===i.bytes,'이미지 업로드 크기 확인 필요',422);const buffer=await blob.arrayBuffer();assert(await digest(buffer)===i.sha256,'이미지 해시가 다릅니다',422);const d=dimensions(new Uint8Array(buffer),i.mime);assert(d.width>0&&d.height>0&&d.width*d.height<=50000000,'해상도 제한',422);if(i.kind==='original')assert(d.width===s.payload.canvas.width&&d.height===s.payload.canvas.height,'원본 좌표 크기 오류',422);images.push({...i,...d,object_path});}
      check(await db.rpc('complete_submission',{p_id:s.id,p_owner:user.id,p_hash:s.payload_hash,p_images:images}));return respond({status:'complete'});
    }
    assert(admin,'관리자 권한이 필요합니다',403);
    if(body.action==='admin-list'){
      let q=db.from('submissions').select('id,owner_id,status,review_status,created_at,completed_at,payload,original_hash').neq('status','pending').order('created_at',{ascending:false}).limit(100);if(body.boss)q=q.eq('payload->>boss',body.boss);if(body.review_status)q=q.eq('review_status',body.review_status);if(body.before)q=q.lt('created_at',body.before);return respond({rows:check(await q)});
    }
    if(body.action==='admin-evidence'){
      assert(uuid.test(body.id),'ID 오류');const s=check(await db.from('submissions').select('*').eq('id',body.id).single());assert(s.status==='complete','완료되지 않은 기록',409);const images=check(await db.from('submission_images').select('*').eq('submission_id',s.id)),signed=[];for(const i of images){const u=check(await db.storage.from('raid-evidence').createSignedUrl(i.object_path,300));signed.push({...i,url:u.signedUrl});}
      const duplicates=check(await db.from('submissions').select('id,created_at,review_status').eq('original_hash',s.original_hash).eq('status','complete').neq('id',s.id));const reviews=check(await db.from('review_events').select('review_status,note,created_at').eq('submission_id',s.id).order('created_at'));return respond({submission:s,images:signed,duplicates,reviews});
    }
    if(body.action==='admin-review'){assert(uuid.test(body.id)&&['unreviewed','accepted','duplicate','rejected'].includes(body.review_status),'검토 상태 오류');check(await db.rpc('review_submission',{p_id:body.id,p_reviewer:user.id,p_status:body.review_status,p_note:String(body.note??'').slice(0,500)}));return respond({ok:true});}
    throw new Problem(400,'지원하지 않는 요청');
  }catch(e){return respond({error:e instanceof Problem?e.message:'서버 요청을 처리하지 못했습니다'},e instanceof Problem?e.status:500);}
});
