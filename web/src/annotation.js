// Original file bytes are retained separately. Labels live below the screenshot.
export async function annotate(canvas,raid){
  await document.fonts.ready;
  const rows=raid.rewards,c=document.createElement('canvas'),font=Math.max(14,Math.round(canvas.width/48)),line=font*1.6;
  c.width=canvas.width;c.height=canvas.height+Math.ceil((rows.length*2+2)*line);const ctx=c.getContext('2d');
  ctx.fillStyle='#111827';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(canvas,0,0);ctx.font=`${font}px "Noto Sans KR", sans-serif`;ctx.lineWidth=Math.max(2,font/5);
  for(let i=0;i<rows.length;i++){
    const r=rows[i];ctx.strokeStyle=r.settlement_excluded?'#9ca3af':'#34d399';ctx.fillStyle=ctx.strokeStyle;
    if(r.box){const {x,y,w,h}=r.box;ctx.strokeRect(x*canvas.width,y*canvas.height,w*canvas.width,h*canvas.height);ctx.fillText(`#${i+1}`,x*canvas.width,Math.max(font,y*canvas.height-4));}
    const y=canvas.height+line*(i*2+1);ctx.fillText(`#${i+1} ${r.reward_name} × ${r.quantity}${r.box?'':' (수동 추가)'}${r.settlement_excluded?' · 정산 제외':''}${r.recognized_reward_id!=null&&r.reward_id!==r.recognized_reward_id?' · 보상 수정':''}${r.ocr_quantity!=null&&r.quantity!==r.ocr_quantity?' · 수량 수정':''}`,12,y);
    ctx.fillStyle='#d1d5db';ctx.fillText(`후보 ${r.candidate_id??'—'} / 점수 ${r.score?.toFixed(3)??'—'} / OCR ${r.ocr_quantity??'—'} / 수량신뢰도 ${r.quantity_confidence?.toFixed(3)??'—'}`,12,y+line);
  }
  const blob=await new Promise(resolve=>c.toBlob(resolve,'image/png'));if(!blob||blob.size>20*1024*1024)throw Error('마킹 이미지가 20MB를 초과합니다. 더 작은 이미지를 사용해 주세요.');return blob;
}
