import {test,expect} from '@playwright/test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
test('real cards produce candidate IDs, names, OCR quantities and confidence',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('./');await expect(page.locator('h1')).toHaveText('보스전 등록');
 await page.locator('#screenshot').setInputFiles(path.join(root,'tests/fixtures/KakaoTalk_20261002_135728198.jpg'));
 await expect(page.locator('#progress')).toHaveText(/템플릿 33개/, {timeout:120000});
 const rows=page.locator('tbody tr');await expect(rows).toHaveCount(6);
 for(let i=0;i<6;i++){
   await expect(rows.nth(i).locator('select')).not.toHaveValue('');
   await expect(rows.nth(i).locator('td').nth(5)).toHaveText(/^U\d\d$/);
 }
 const values=await page.locator('[data-qty]').evaluateAll(els=>els.map(x=>Number(x.value)));
 expect(values).toEqual([800,150,150,120,120,5]);
 expect(errors).toEqual([]);
 await page.locator('#save-raid').click();await page.locator('[data-tab="records"]').click();
 await expect(page.locator('tbody tr')).toHaveCount(1);
 await page.locator('[data-tab="summary"]').click();await expect(page.locator('tbody tr')).toHaveCount(3);
 await page.screenshot({path:'test-results/summary.png',fullPage:true});
});
test('member and reward updates persist across reload, referenced deletion is blocked',async({page})=>{
 await page.goto('./');await page.locator('[data-tab="members"]').click();
 await page.locator('#member-add input').fill('새 참여자');await page.locator('#member-add button').click();
 await expect(page.locator('tbody tr')).toHaveCount(6);
 await page.locator('[data-member-name="6"]').fill('참여자 수정');await page.locator('[data-save-member="6"]').click();await expect(page.locator('[data-save-member="6"]')).toBeEnabled();
 await page.locator('[data-member-active="6"]').uncheck();await page.locator('[data-save-member="6"]').click();await expect(page.locator('[data-save-member="6"]')).toBeEnabled();
 await page.reload();await page.locator('[data-tab="members"]').click();
 await expect(page.locator('[data-member-name="6"]')).toHaveValue('참여자 수정');await expect(page.locator('[data-member-active="6"]')).not.toBeChecked();
 page.on('dialog',d=>d.accept());await page.locator('[data-delete-member="6"]').click();await expect(page.locator('tbody tr')).toHaveCount(5);
 await page.locator('[data-tab="rewards"]').click();await page.locator('[data-r-value="5"]').fill('1234');await page.locator('[data-r-enabled="5"]').uncheck();await page.locator('[data-save-reward="5"]').click();await expect(page.locator('[data-save-reward="5"]')).toBeEnabled();
 await page.reload();await page.locator('[data-tab="rewards"]').click();await expect(page.locator('[data-r-value="5"]')).toHaveValue('1234');await expect(page.locator('[data-r-enabled="5"]')).not.toBeChecked();
 await page.screenshot({path:'test-results/rewards.png',fullPage:true});
});
