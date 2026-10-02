import { createWorker, PSM } from 'tesseract.js';
const base=new URL(import.meta.env.BASE_URL, document.baseURI).href;
let cvPromise,workerPromise;
export function loadCV(){
  if(!cvPromise)cvPromise=new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src=`${base}vendor/opencv.js`;
    script.onerror=()=>reject(Error('카드 검출 엔진을 불러오지 못했습니다. 새로고침해 주세요.'));
    const timeout=setTimeout(()=>reject(Error('카드 검출 엔진 로딩 시간 초과')),60000);
    script.onload=async()=>{
      let cv=window.cv;
      if(cv?.then)cv=await cv;
      if(cv?.Mat){clearTimeout(timeout);resolve(cv);}
      else if(cv)cv.onRuntimeInitialized=()=>{clearTimeout(timeout);resolve(cv);};
      else {clearTimeout(timeout);reject(Error('검출 엔진 초기화 실패'));}
    };
    document.head.append(script);
  });return cvPromise;
}
export async function imageCanvas(source){
  const image=new Image();image.src=typeof source==='string'?source:URL.createObjectURL(source);
  try{await image.decode();const c=document.createElement('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;c.getContext('2d').drawImage(image,0,0);return c;}
  finally{if(typeof source!=='string')URL.revokeObjectURL(image.src);}
}
function cropCanvas(canvas,b){const c=document.createElement('canvas');c.width=b.w;c.height=b.h;c.getContext('2d').drawImage(canvas,b.x,b.y,b.w,b.h,0,0,b.w,b.h);return c;}
function iou(a,b){const inter=Math.max(0,Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x))*Math.max(0,Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y));return inter/(a.w*a.h+b.w*b.h-inter);}
export async function detectCards(canvas){
  const cv=await loadCV(),src=cv.imread(canvas),gray=new cv.Mat(),edges=new cv.Mat(),contours=new cv.MatVector(),hierarchy=new cv.Mat();
  try{
    cv.cvtColor(src,gray,cv.COLOR_RGBA2GRAY);cv.Canny(gray,edges,40,150);cv.findContours(edges,contours,hierarchy,cv.RETR_LIST,cv.CHAIN_APPROX_SIMPLE);
    const H=canvas.height,W=canvas.width,boxes=[];
    for(let i=0;i<contours.size();i++){
      const c=contours.get(i);try{const b=cv.boundingRect(c),{x,y,width:w,height:h}=b;
        if(w>=.065*W&&w<=.155*W&&h>=.065*W&&h<=.165*W&&w/h>=.8&&w/h<=1.2&&x>=.06*W&&x<=.94*W&&y>=.28*H&&y<=.61*H&&cv.contourArea(c)>=.62*w*h)boxes.push({x,y,w,h});
      }finally{c.delete();}
    }
    const kept=[];for(const b of boxes.sort((a,b)=>b.w*b.h-a.w*a.h))if(kept.every(k=>iou(b,k)<.7))kept.push(b);
    const sizes=kept.map(b=>b.w).sort((a,b)=>a-b),n=sizes.length;
    const median=n%2?sizes[Math.floor(n/2)]:(sizes[n/2-1]+sizes[n/2])/2;
    return kept.filter(b=>b.w>=.78*median&&b.w<=1.22*median&&b.h>=.78*median&&b.h<=1.22*median).sort((a,b)=>a.y-b.y||a.x-b.x).map(b=>({box:b,canvas:cropCanvas(canvas,b)}));
  }finally{src.delete();gray.delete();edges.delete();contours.delete();hierarchy.delete();}
}
function median(values){values.sort((a,b)=>a-b);return values.length%2?values[Math.floor(values.length/2)]:(values[values.length/2-1]+values[values.length/2])/2;}
export async function describe(canvas){
  const cv=await loadCV(),rgba=cv.imread(canvas),rgb=new cv.Mat(),hsv=new cv.Mat(),resized=new cv.Mat(),lab=new cv.Mat();let roi;
  try{
    cv.cvtColor(rgba,rgb,cv.COLOR_RGBA2RGB);cv.cvtColor(rgb,hsv,cv.COLOR_RGB2HSV);
    const W=canvas.width,H=canvas.height,hues=[],sats=[];
    for(const [left,right] of [[.08,.22],[.78,.92]])for(let y=Math.floor(.12*H);y<Math.floor(.24*H);y++)for(let x=Math.floor(left*W);x<Math.floor(right*W);x++){
      const i=(y*W+x)*3;if(hsv.data[i+1]>35&&hsv.data[i+2]>45){hues.push(hsv.data[i]);sats.push(hsv.data[i+1]);}
    }
    let rarity='GRAY';if(hues.length){const hue=median(hues),sat=median(sats);if(sat>=70)rarity=hue<8||hue>=170?'RED':hue<25?'YELLOW':hue<85?'GREEN':hue<125?'BLUE':'PURPLE';}
    const x=Math.floor(.12*W),y=Math.floor(.12*H);roi=rgb.roi(new cv.Rect(x,y,Math.floor(.88*W)-x,Math.floor(.72*H)-y));
    cv.resize(roi,resized,new cv.Size(48,48),0,0,cv.INTER_AREA);cv.cvtColor(resized,lab,cv.COLOR_RGB2Lab);
    const values=Float32Array.from(lab.data),mean=values.reduce((a,b)=>a+b,0)/values.length;
    let norm=0;for(let i=0;i<values.length;i++){values[i]-=mean;norm+=values[i]*values[i];}norm=Math.sqrt(norm);
    if(norm>1e-8)for(let i=0;i<values.length;i++)values[i]/=norm;
    return {values,rarity};
  }finally{roi?.delete();rgba.delete();rgb.delete();hsv.delete();resized.delete();lab.delete();}
}
export function compare(a,b){let dot=0;for(let i=0;i<a.values.length;i++)dot+=a.values[i]*b.values[i];return .82*Math.max(0,Math.min(1,(dot+1)/2))+.18*(a.rarity===b.rarity?1:0);}
export async function readQuantity(canvas){
  if(!workerPromise)workerPromise=createWorker('eng',1,{workerPath:`${base}vendor/worker.min.js`,corePath:`${base}vendor/core`,langPath:`${base}vendor`,workerBlobURL:false}).catch(e=>{workerPromise=null;throw e;});
  const worker=await workerPromise;await worker.setParameters({tessedit_char_whitelist:'0123456789',tessedit_pageseg_mode:PSM.SINGLE_LINE});
  const W=canvas.width,H=canvas.height,roi=document.createElement('canvas');
  roi.width=Math.max(1,Math.floor(.9*W))*5;roi.height=Math.max(1,Math.floor(.27*H))*5;
  roi.getContext('2d').drawImage(canvas,Math.floor(.05*W),Math.floor(.71*H),Math.floor(.9*W),Math.floor(.27*H),0,0,roi.width,roi.height);
  const cv=await loadCV(),src=cv.imread(roi),rgb=new cv.Mat(),hsv=new cv.Mat(),mask=new cv.Mat(),inverted=new cv.Mat(),padded=new cv.Mat();
  const low=new cv.Mat(src.rows,src.cols,cv.CV_8UC3,new cv.Scalar(0,0,170)),high=new cv.Mat(src.rows,src.cols,cv.CV_8UC3,new cv.Scalar(180,90,255));
  try{
    cv.cvtColor(src,rgb,cv.COLOR_RGBA2RGB);cv.cvtColor(rgb,hsv,cv.COLOR_RGB2HSV);cv.inRange(hsv,low,high,mask);cv.bitwise_not(mask,inverted);
    cv.copyMakeBorder(inverted,padded,18,18,18,18,cv.BORDER_CONSTANT,new cv.Scalar(255));
    const target=document.createElement('canvas');cv.imshow(target,padded);
    const {data}=await worker.recognize(target);const text=data.text.trim();
    return /^\d+$/.test(text)&&data.confidence>=30?{quantity:Number(text),confidence:data.confidence/100}:{quantity:null,confidence:0};
  }finally{src.delete();rgb.delete();hsv.delete();mask.delete();inverted.delete();padded.delete();low.delete();high.delete();}
}

let descriptors;
export async function loadTemplates(seed){
  if(!descriptors)descriptors=Promise.all(seed.templates.map(async t=>({...t,descriptor:await describe(await imageCanvas(`${base}${t.path}`))})));
  return descriptors;
}
export async function recognize(canvas,state,seed,onProgress=()=>{}){
  const templates=await loadTemplates(seed),cards=await detectCards(canvas),output=[];
  for(let i=0;i<cards.length;i++){
    onProgress(`보상 ${i+1}/${cards.length} 인식 중`);const card=cards[i],description=await describe(card.canvas);
    const candidates=templates.map(t=>({...t,score:compare(description,t.descriptor)})).sort((a,b)=>b.score-a.score),best=candidates[0];
    const reward=state.rewards.find(r=>r.id===best.reward_id),accepted=best.score>=state.settings.match_threshold;
    const mode=accepted?reward.quantity_mode:'AUTO';let raw=null,confidence=null,status='기본 1개 (OCR 미사용)';
    if(mode!=='DEFAULT_ONE')try{const q=await readQuantity(card.canvas);raw=q.quantity;confidence=q.confidence;status=raw===null?'OCR 실패: 수량 확인 필요':'OCR 인식';}catch(e){status=`OCR 실패: 수량 확인 필요 (${e.message})`;}
    output.push({box:{x:card.box.x/canvas.width,y:card.box.y/canvas.height,w:card.box.w/canvas.width,h:card.box.h/canvas.height},recognized_reward_id:accepted?reward.id:null,reward_id:accepted?reward.id:null,quantity:raw??1,ocr_quantity:raw,score:best.score,
      candidate_id:best.candidate_id,candidate_name:reward.name,quantity_confidence:confidence,rarity:description.rarity,
      match_status:accepted?(reward.enabled?'자동매칭':'비활성 보상: 교체 필요'):'낮은 점수: 보상 확인 필요',quantity_status:status,thumbnail:card.canvas.toDataURL()});
  }
  return output;
}
