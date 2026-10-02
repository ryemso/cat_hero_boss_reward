import { test } from 'node:test';
import assert from 'node:assert/strict';
import {summarize,validateName,validateState,deleteMember} from './domain.js';
import fs from 'node:fs';
const seed=JSON.parse(fs.readFileSync(new URL('../public/seed.json',import.meta.url),'utf8'));
test('same Excel valuation, equal shares, exclusion and inactive history',()=>{
 const state=structuredClone(seed),blue=state.rewards.find(r=>r.name==='파템'),excluded=state.rewards.find(r=>r.name==='빨레');
 excluded.unit_value=999999;state.members[0].active=false;
 state.raids.push({id:1,date:'2026-10-02',time:'15:00',member_ids:[1,2],rewards:[{reward_id:blue.id,quantity:2},{reward_id:excluded.id,quantity:1}]});
 assert.deepEqual(summarize(state).map(r=>r.합산가치),[4300,4300]);assert.equal(summarize(state)[0]['수수료 제외'],19350);
 assert.throws(()=>deleteMember(state,1));state.members.push({id:6,name:'추가',active:true});deleteMember(state,6);assert.equal(state.members.length,5);
 blue.distribution_type='PER_PERSON';assert.equal(summarize(state)[0].합산가치,8600);
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
