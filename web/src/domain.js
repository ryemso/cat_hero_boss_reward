export const EXCEL_COLUMNS=['파템','초템','흰템','전설픽업','동료소환','룬 소환','랜덤 룬','보라레시피','파랑레시피','초록레시피'];
export function validateName(name,items,id){
  name=String(name??'').trim();
  if(!name)throw Error('이름을 입력해 주세요.');
  if(items.some(x=>x.id!==id&&x.name===name))throw Error('이미 사용 중인 이름입니다.');
  return name;
}
export function deleteMember(state,id){
  if(state.raids.some(r=>r.member_ids.includes(id)))throw Error('정산 기록이 있는 참여자는 비활성화해 주세요.');
  state.members=state.members.filter(m=>m.id!==id);
}
export function summarize(state,from='',to='9999-12-31'){
  const output=new Map();
  for(const raid of state.raids.filter(r=>r.date>=from&&r.date<=to)){
    for(const mid of raid.member_ids){
      const member=state.members.find(m=>m.id===mid);if(!member)continue;
      if(!output.has(mid))output.set(mid,{member:member.name,...Object.fromEntries(EXCEL_COLUMNS.map(c=>[c,0])),합산가치:0});
      const row=output.get(mid);
      for(const item of raid.rewards){
        const reward=state.rewards.find(r=>r.id===item.reward_id);
        if(!reward||reward.settlement_column==='__EXCLUDE__')continue;
        const share=item.quantity/(reward.distribution_type==='PER_PERSON'?1:raid.member_ids.length);
        row[reward.settlement_column]=(row[reward.settlement_column]||0)+share;
        row.합산가치+=share*reward.unit_value;
      }
    }
  }
  return [...output.values()].map(row=>({...row,현금:row.합산가치*state.settings.cash_per_100_value/100,
    '수수료 제외':row.합산가치*state.settings.cash_per_100_value/100*(1-state.settings.fee_rate)}));
}
export function validateState(state,seed){
  if(!state||state.schemaVersion!==1)throw Error('지원하지 않는 백업 형식입니다.');
  for(const key of ['members','rewards','raids','templates','bosses'])if(!Array.isArray(state[key]))throw Error(`백업 ${key} 확인 필요`);
  for(const key of ['members','rewards','raids']){
    const ids=state[key].map(x=>x.id);if(ids.some(x=>!Number.isInteger(x)||x<=0)||new Set(ids).size!==ids.length)throw Error('백업 ID 오류');
  }
  for(const key of ['members','rewards']){
    const names=state[key].map(x=>x.name);if(names.some(n=>typeof n!=='string'||!n.trim())||new Set(names).size!==names.length)throw Error('백업 이름 오류');
  }
  for(const member of state.members)if(typeof member.active!=='boolean')throw Error('참여자 활성 상태 오류');
  for(const r of state.rewards)if(!Number.isFinite(r.unit_value)||r.unit_value<0||!['AUTO','OCR','DEFAULT_ONE'].includes(r.quantity_mode)||!['EQUAL','PER_PERSON'].includes(r.distribution_type)||typeof r.enabled!=='boolean')throw Error('보상 설정 오류');
  for(const t of seed.templates){
    const imported=state.templates.find(x=>x.candidate_id===t.candidate_id), original=seed.rewards.find(r=>r.id===t.reward_id);
    const reward=state.rewards.find(r=>r.id===imported?.reward_id);
    if(!imported||!reward||reward.settlement_column!==original.settlement_column||imported.path!==t.path)throw Error('U01~U33 정산 매핑을 유지해야 합니다.');
  }
  if(state.templates.length!==seed.templates.length)throw Error('템플릿 개수가 다릅니다.');
  for(const raid of state.raids){
    if(!Array.isArray(raid.member_ids)||!raid.member_ids.length||new Set(raid.member_ids).size!==raid.member_ids.length||raid.member_ids.some(id=>!state.members.some(m=>m.id===id)))throw Error('참여자 연결 오류');
    if(!Array.isArray(raid.rewards)||!raid.rewards.length||raid.rewards.some(r=>!state.rewards.some(x=>x.id===r.reward_id)||!Number.isFinite(r.quantity)||r.quantity<0))throw Error('보상 연결 오류');
    if(!/^\d{4}-\d{2}-\d{2}$/.test(raid.date)||!/^\d{2}:\d{2}$/.test(raid.time))throw Error('날짜/시간 오류');
  }
  if(!state.settings||!Number.isFinite(state.settings.cash_per_100_value)||state.settings.cash_per_100_value<0||!Number.isFinite(state.settings.fee_rate)||state.settings.fee_rate<0||state.settings.fee_rate>1||!Number.isFinite(state.settings.match_threshold)||state.settings.match_threshold<0.5||state.settings.match_threshold>0.99)throw Error('환산/인식 설정 오류');
  return state;
}
