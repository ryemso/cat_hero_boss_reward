"""Build browser seeds from the original U01~U33 CSV; never maintain a second mapping."""
import csv,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
public=root/'web/public';public.mkdir(parents=True,exist_ok=True)
shutil.copytree(root/'data/starter_templates',public/'templates',dirs_exist_ok=True)
rewards=[];templates=[]
with (root/'data/starter_mapping.csv').open(encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        name=row['실제_보상명']
        reward=next((r for r in rewards if r['name']==name),None)
        if not reward:
            reward={'id':len(rewards)+1,'name':name,'settlement_column':row['정산_컬럼'],
                    'unit_value':float(row['1단위당_보라가치']),'quantity_mode':row['수량방식(AUTO/OCR/DEFAULT_ONE)'],
                    'distribution_type':'EQUAL','rarity':'UNKNOWN','enabled':True}
            rewards.append(reward)
        templates.append({'candidate_id':row['candidate_id'],'reward_id':reward['id'],'path':f"templates/{row['candidate_id']}.png"})
seed={'schemaVersion':1,'members':[{'id':i+1,'name':name,'active':True} for i,name in enumerate(['인솔','로티','초코','림','준일'])],
      'bosses':['루니','캣토이','바나나'],'rewards':rewards,'templates':templates,'raids':[],
      'settings':{'cash_per_100_value':500,'fee_rate':0.1,'match_threshold':0.78}}
(public/'seed.json').write_text(json.dumps(seed,ensure_ascii=False,indent=2))
vendor=public/'vendor';vendor.mkdir(exist_ok=True)
modules=root/'web/node_modules'
shutil.copy(modules/'@techstark/opencv-js/dist/opencv.js',vendor/'opencv.js')
shutil.copy(modules/'tesseract.js/dist/worker.min.js',vendor/'worker.min.js')
shutil.copytree(modules/'tesseract.js-core',vendor/'core',dirs_exist_ok=True)
eng=list((modules/'@tesseract.js-data/eng').rglob('eng.traineddata.gz'))
fast=next((p for p in eng if 'best_int' in str(p)),eng[0])
shutil.copy(fast,vendor/'eng.traineddata.gz')
print(f'Built {len(templates)} templates / {len(rewards)} rewards; OCR assets hosted locally.')
