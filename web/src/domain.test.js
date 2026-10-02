import { test } from 'node:test';
import assert from 'node:assert/strict';
import {summarize,validateName,validateState,deleteMember} from './domain.js';
import fs from 'node:fs';
const seed=JSON.parse(fs.readFileSync(new URL('../public/seed.json',import.meta.url),'utf8'));
test('same Excel valuation, equal shares, included red rewards and inactive history',()=>{
 const state=structuredClone(seed),blue=state.rewards.find(r=>r.name==='파템'),excluded=state.rewards.find(r=>r.name==='빨레');
 excluded.unit_value=999999;state.members[0].active=false;
 state.raids.push({id:1,date:'2026-10-02',time:'15:00',member_ids:[1,2],rewards:[{reward_id:blue.id,quantity:2},{reward_id:excluded.id,quantity:1}]});
 assert.deepEqual(summarize(state).map(r=>r.합산가치),[504299.5,504299.5]);assert.equal(summarize(state)[0]['수수료 제외'],2269347.75);
 assert.throws(()=>deleteMember(state,1));state.members.push({id:6,name:'추가',active:true});deleteMember(state,6);assert.equal(state.members.length,5);
 blue.distribution_type='PER_PERSON';assert.equal(summarize(state)[0].합산가치,508599.5);
});
test('backup validation preserves all U IDs and renamed reward',()=>{
 const state=structuredClone(seed);state.rewards[0].name='이름 변경';assert.equal(validateState(state,seed),state);
 state.templates[0].reward_id=state.rewards[1].id;assert.throws(()=>validateState(state,seed));
});
test('reject corrupt backups and duplicate names',()=>{
 assert.throws(()=>validateName('인솔',seed.members));assert.throws(()=>validateName(' ',seed.members));
 const state=structuredClone(seed);state.rewards[0].unit_value=-1;assert.throws(()=>validateState(state,seed));
 const invalid=structuredClone(seed);invalid.raids=[{id:1,date:'2026-10-02',time:'15:00',member_ids:[999],rewards:[{reward_id:1,quantity:1}]}];assert.throws(()=>validateState(invalid,seed));
});

test('legacy red and purple inclusion preserves custom names and values',()=>{
 const state=structuredClone(seed);for(const cid of ['U01','U20']){const r=state.rewards.find(r=>r.id===state.templates.find(t=>t.candidate_id===cid).reward_id);r.settlement_column='__EXCLUDE__';r.name+=' 수정';r.unit_value=100;}
 validateState(state,seed);state.raids.push({id:1,date:'2026-10-02',time:'15:00',member_ids:[1,2],rewards:['U01','U20'].map(cid=>({reward_id:state.templates.find(t=>t.candidate_id===cid).reward_id,quantity:2}))});
 const result=summarize(state)[0];assert.equal(result['빨레'],1);assert.equal(result['보'],1);assert.equal(result.합산가치,200);
});
