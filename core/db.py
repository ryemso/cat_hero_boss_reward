from __future__ import annotations
import sqlite3
import csv
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "settlement.db"
STARTER_MAPPING = ROOT / "data" / "starter_mapping.csv"
STARTER_TEMPLATE_DIR = ROOT / "data" / "starter_templates"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS bosses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS reward_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    settlement_column TEXT NOT NULL,
    rarity TEXT NOT NULL DEFAULT 'UNKNOWN',
    template_path TEXT,
    quantity_mode TEXT NOT NULL DEFAULT 'AUTO',
    distribution_type TEXT NOT NULL DEFAULT 'EQUAL',
    unit_value REAL NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reward_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reward_id INTEGER NOT NULL,
    candidate_id TEXT UNIQUE,
    template_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (reward_id) REFERENCES reward_master(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS raids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raid_date TEXT NOT NULL,
    raid_time TEXT NOT NULL,
    boss_id INTEGER,
    memo TEXT,
    screenshot_name TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (boss_id) REFERENCES bosses(id)
);
CREATE TABLE IF NOT EXISTS raid_members (
    raid_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    PRIMARY KEY (raid_id, member_id),
    FOREIGN KEY (raid_id) REFERENCES raids(id) ON DELETE CASCADE,
    FOREIGN KEY (member_id) REFERENCES members(id)
);
CREATE TABLE IF NOT EXISTS raid_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raid_id INTEGER NOT NULL,
    reward_id INTEGER,
    reward_name_snapshot TEXT NOT NULL,
    quantity REAL NOT NULL,
    ocr_quantity REAL,
    recognition_score REAL,
    confirmed INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (raid_id) REFERENCES raids(id) ON DELETE CASCADE,
    FOREIGN KEY (reward_id) REFERENCES reward_master(id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_MEMBERS = ["인솔", "로티", "초코", "림", "준일"]
DEFAULT_BOSSES = ["루니", "캣토이", "바나나"]
DEFAULT_SETTINGS = {
    "cash_per_100_value": "500",
    "fee_rate": "0.10",
    "match_threshold": "0.78",
}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _seed_starter_rewards(con: sqlite3.Connection) -> None:
    """사용자가 확정한 U01~U33 매핑을 최초 실행 시 자동 등록한다.

    동일한 정산 보상(예: U05~U08의 '파')은 reward_master 1개에
    여러 reward_templates를 연결한다.
    """
    if not STARTER_MAPPING.exists():
        return
    now = datetime.now().isoformat(timespec="seconds")
    with STARTER_MAPPING.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = (row.get("candidate_id") or "").strip()
            name = (row.get("실제_보상명") or "").strip()
            settlement_col = (row.get("정산_컬럼") or name).strip()
            quantity_mode = (row.get("수량방식(AUTO/OCR/DEFAULT_ONE)") or "AUTO").strip().upper()
            try:
                unit_value = float((row.get("1단위당_보라가치") or "0").strip() or 0)
            except ValueError:
                unit_value = 0.0
            if not cid or not name:
                continue
            template_path = STARTER_TEMPLATE_DIR / f"{cid}.png"
            if not template_path.exists():
                continue
            existing_template = con.execute('SELECT reward_id FROM reward_templates WHERE candidate_id=?', (cid,)).fetchone()
            if existing_template:
                # A renamed reward remains attached to its original U candidate.
                continue
            con.execute(
                """INSERT OR IGNORE INTO reward_master
                (name,settlement_column,rarity,template_path,quantity_mode,distribution_type,unit_value,enabled,created_at)
                VALUES(?,?,?,?,?,'EQUAL',?,1,?)""",
                (name, settlement_col, 'UNKNOWN', template_path.relative_to(ROOT).as_posix(), quantity_mode, unit_value, now),
            )
            reward = con.execute("SELECT id FROM reward_master WHERE name=?", (name,)).fetchone()
            if reward:
                rid = int(reward[0])
                # 기존 단일-template 구조와도 호환되도록 대표 template_path를 유지한다.
                con.execute(
                    """INSERT OR IGNORE INTO reward_templates
                    (reward_id,candidate_id,template_path,created_at) VALUES(?,?,?,?)""",
                    (rid, cid, template_path.relative_to(ROOT).as_posix(), now),
                )


def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        first_run = not con.execute("SELECT 1 FROM settings WHERE key='defaults_initialized'").fetchone()
        if first_run:
            for name in DEFAULT_MEMBERS:
                con.execute("INSERT OR IGNORE INTO members(name) VALUES (?)", (name,))
            con.execute("INSERT INTO settings(key,value) VALUES('defaults_initialized','1')")
        for name in DEFAULT_BOSSES:
            con.execute("INSERT OR IGNORE INTO bosses(name) VALUES (?)", (name,))
        for k, v in DEFAULT_SETTINGS.items():
            con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        _seed_starter_rewards(con)
        # Repair paths saved by earlier machines/install locations without changing U IDs.
        for table in ('reward_master', 'reward_templates'):
            for row in con.execute(f"SELECT id,template_path FROM {table} WHERE template_path IS NOT NULL").fetchall():
                path = resolve_template_path(row['template_path'])
                if path.exists():
                    try:
                        stored = path.relative_to(ROOT).as_posix()
                    except ValueError:
                        stored = str(path)
                    con.execute(f"UPDATE {table} SET template_path=? WHERE id=?", (stored, row['id']))
        existing = {r[1] for r in con.execute('PRAGMA table_info(raid_rewards)')}
        for column, kind in [('candidate_id','TEXT'), ('quantity_confidence','REAL'), ('rarity','TEXT')]:
            if column not in existing:
                con.execute(f'ALTER TABLE raid_rewards ADD COLUMN {column} {kind}')
        con.commit()


def rows(sql: str, params=()):
    with connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def scalar(sql: str, params=(), default=None):
    with connect() as con:
        r = con.execute(sql, params).fetchone()
        return r[0] if r else default


def execute(sql: str, params=()):
    with connect() as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid


def setting(key: str, default=None):
    return scalar("SELECT value FROM settings WHERE key=?", (key,), default)


def set_setting(key: str, value) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        con.commit()


def save_raid(raid_date, raid_time, boss_id, member_ids, rewards, memo="", screenshot_name=None):
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as con:
        cur = con.execute(
            "INSERT INTO raids(raid_date,raid_time,boss_id,memo,screenshot_name,created_at) VALUES(?,?,?,?,?,?)",
            (str(raid_date), str(raid_time), boss_id, memo, screenshot_name, now),
        )
        raid_id = cur.lastrowid
        for mid in member_ids:
            con.execute("INSERT INTO raid_members(raid_id,member_id) VALUES(?,?)", (raid_id, int(mid)))
        for r in rewards:
            con.execute(
                """INSERT INTO raid_rewards
                (raid_id,reward_id,reward_name_snapshot,quantity,ocr_quantity,recognition_score,candidate_id,quantity_confidence,rarity,confirmed)
                VALUES(?,?,?,?,?,?,?,?,?,1)""",
                (
                    raid_id,
                    r.get("reward_id") or None,
                    r.get("reward_name") or "미지정",
                    float(r.get("quantity") or 0),
                    None if r.get("ocr_quantity") in (None, "") else float(r.get("ocr_quantity")),
                    None if r.get("score") in (None, "") else float(r.get("score")),
                    r.get('candidate_id'), r.get('quantity_confidence'), r.get('rarity'),
                ),
            )
        con.commit()
    return raid_id


def delete_raid(raid_id: int):
    with connect() as con:
        con.execute("DELETE FROM raids WHERE id=?", (int(raid_id),))
        con.commit()


def resolve_template_path(value):
    normalized = str(value or '').replace('\\', '/')
    path = Path(normalized)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file():
        return path
    # Old absolute paths (including Windows drive paths) follow the project on relocation.
    for folder in ('starter_templates', 'templates'):
        if f'/{folder}/' in normalized:
            return ROOT / 'data' / folder / normalized.rsplit('/', 1)[-1]
    return path


def get_templates():
    result = rows("""SELECT rm.id,rm.name,rm.settlement_column,rm.rarity,rm.quantity_mode,
        rm.distribution_type,rm.unit_value,rm.enabled,rt.candidate_id,rt.template_path
        FROM reward_templates rt JOIN reward_master rm ON rm.id=rt.reward_id
        ORDER BY rt.candidate_id,rt.id""")
    # Keep legacy single-template/custom rewards alongside U01~U33.
    result += rows("""SELECT rm.*, NULL candidate_id FROM reward_master rm
        WHERE rm.template_path IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM reward_templates rt WHERE rt.reward_id=rm.id)""")
    for item in result:
        item['template_path'] = str(resolve_template_path(item['template_path']))
    return result


def save_member(member_id, name, active=True):
    name = name.strip()
    if not name:
        raise ValueError('참여자 이름을 입력해 주세요.')
    with connect() as con:
        if member_id is None:
            con.execute('INSERT INTO members(name,active) VALUES(?,?)', (name,int(active)))
        else:
            con.execute('UPDATE members SET name=?,active=? WHERE id=?', (name,int(active),member_id))


def delete_member(member_id):
    with connect() as con:
        if con.execute('SELECT 1 FROM raid_members WHERE member_id=? LIMIT 1',(member_id,)).fetchone():
            raise ValueError('정산 기록이 있는 참여자는 삭제할 수 없습니다. 비활성화하면 기록을 보존할 수 있습니다.')
        con.execute('DELETE FROM members WHERE id=?',(member_id,))


def update_reward(reward_id, name, settlement_column, rarity, quantity_mode, distribution_type, unit_value, enabled):
    if not name.strip() or not settlement_column.strip():
        raise ValueError('보상명과 정산 컬럼을 입력해 주세요.')
    if quantity_mode not in ('AUTO','OCR','DEFAULT_ONE') or distribution_type not in ('EQUAL','PER_PERSON'):
        raise ValueError('수량/분배 방식을 확인해 주세요.')
    import math
    if not math.isfinite(float(unit_value)) or float(unit_value)<0:
        raise ValueError('값어치는 0 이상의 숫자여야 합니다.')
    with connect() as con:
        old = con.execute('SELECT settlement_column FROM reward_master WHERE id=?',(reward_id,)).fetchone()
        linked = {r[0] for r in con.execute('SELECT candidate_id FROM reward_templates WHERE reward_id=?', (reward_id,))}
        if linked and STARTER_MAPPING.exists():
            with STARTER_MAPPING.open(encoding='utf-8-sig', newline='') as f:
                required = {r['정산_컬럼'] for r in csv.DictReader(f) if r['candidate_id'] in linked}
            if required and settlement_column not in required:
                raise ValueError('U01~U33 정산 컬럼 매핑은 유지해야 합니다.')
        con.execute("""UPDATE reward_master SET name=?,settlement_column=?,rarity=?,quantity_mode=?,
            distribution_type=?,unit_value=?,enabled=? WHERE id=?""",
            (name.strip(),settlement_column.strip(),rarity,quantity_mode,distribution_type,float(unit_value),int(enabled),reward_id))
