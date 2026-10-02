"""Package source for installation; never include user databases, dependencies or caches."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
with ZipFile(root/'boss_settlement_install.zip','w',ZIP_DEFLATED) as z:
    for item in root.rglob('*'):
        rel=item.relative_to(root)
        if not item.is_file() or any(p in {'.git','.venv','__pycache__','node_modules','public','dist','test-results','playwright-report'} for p in rel.parts):continue
        if item.suffix in {'.zip','.pyc'} or 'settlement.db' in item.name:continue
        if rel.parts[:2]==('data','templates') and item.name!='.gitkeep':continue
        z.write(item,Path('boss_settlement_v1')/rel)
print(root/'boss_settlement_install.zip')
