let dbPromise;
function database(){return dbPromise??=new Promise((resolve,reject)=>{const r=indexedDB.open('cat-hero-ledger',1);r.onupgradeneeded=()=>{r.result.createObjectStore('state');r.result.createObjectStore('outbox',{keyPath:'id'});};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
async function transaction(stores,mode,run){const db=await database();return new Promise((resolve,reject)=>{const tx=db.transaction(stores,mode);let result;try{result=run(tx);}catch(e){tx.abort();reject(e);return;}tx.oncomplete=()=>resolve(typeof result==='function'?result():result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error??Error('저장이 취소됐습니다.'));});}
export function readState(){return transaction(['state'],'readonly',tx=>{const r=tx.objectStore('state').get('ledger');return ()=>r.result;});}
export function saveState(state,job){return transaction(['state','outbox'],'readwrite',tx=>{tx.objectStore('state').put(state,'ledger');if(job){const {replace,...entry}=job;tx.objectStore('outbox')[replace?'put':'add'](entry);}});}
export function jobs(){return transaction(['outbox'],'readonly',tx=>{const r=tx.objectStore('outbox').getAll();return ()=>r.result;});}
export function putJob(job){return transaction(['outbox'],'readwrite',tx=>{tx.objectStore('outbox').put(job);});}
export async function cancelJob(id){return transaction(['outbox'],'readwrite',tx=>{const s=tx.objectStore('outbox'),r=s.get(id);r.onsuccess=()=>{if(r.result)s.put({...r.result,action:'withdraw',state:'pending',next:0,blobs:null});};});}
export function compactJob(job){return putJob({...job,state:'complete',blobs:null,error:null});}
