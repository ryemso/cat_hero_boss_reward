from __future__ import annotations
import pandas as pd
from . import db


def detail_rows(date_from=None, date_to=None):
    where = []
    params = []
    if date_from:
        where.append("r.raid_date >= ?")
        params.append(str(date_from))
    if date_to:
        where.append("r.raid_date <= ?")
        params.append(str(date_to))
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
    SELECT r.id raid_id, r.raid_date, r.raid_time, b.name boss,
           m.id member_id, m.name member,
           rr.reward_id, rr.reward_name_snapshot reward_name, rr.quantity,
           rr.ocr_quantity, rr.recognition_score, rr.candidate_id, rr.quantity_confidence, rr.rarity,
           COALESCE(rm.distribution_type,'EQUAL') distribution_type,
           COALESCE(rm.settlement_column, rr.reward_name_snapshot) settlement_column,
           COALESCE(rm.unit_value,0) unit_value,
           (SELECT COUNT(*) FROM raid_members x WHERE x.raid_id=r.id) participant_count
    FROM raids r
    LEFT JOIN bosses b ON b.id=r.boss_id
    JOIN raid_members rmbr ON rmbr.raid_id=r.id
    JOIN members m ON m.id=rmbr.member_id
    JOIN raid_rewards rr ON rr.raid_id=r.id
    LEFT JOIN reward_master rm ON rm.id=rr.reward_id
    {where_sql}
    ORDER BY r.raid_date, r.raid_time, r.id, m.name
    """
    data = db.rows(sql, params)
    if not data:
        return pd.DataFrame(columns=["raid_id","raid_date","raid_time","boss","member","reward_name","settlement_column","share_qty","unit_value","value"])
    df = pd.DataFrame(data)
    def share(row):
        kind = str(row["distribution_type"]).upper()
        if kind == "PER_PERSON":
            return float(row["quantity"])
        count = max(int(row["participant_count"]), 1)
        return float(row["quantity"]) / count
    df["share_qty"] = df.apply(share, axis=1)
    df.loc[df["settlement_column"] == "__EXCLUDE__", "unit_value"] = 0
    df["value"] = df["share_qty"] * pd.to_numeric(df["unit_value"], errors="coerce").fillna(0)
    return df


def member_summary(date_from=None, date_to=None):
    df = detail_rows(date_from, date_to)
    if df.empty:
        return pd.DataFrame(columns=["member","total_value","cash","after_fee"])
    cash_per_100 = float(db.setting("cash_per_100_value", 500))
    fee_rate = float(db.setting("fee_rate", 0.10))
    s = df.groupby("member", as_index=False)["value"].sum().rename(columns={"value":"total_value"})
    s["cash"] = s["total_value"] * cash_per_100 / 100.0
    s["after_fee"] = s["cash"] * (1.0 - fee_rate)
    return s.sort_values("member").reset_index(drop=True)


def member_item_pivot(date_from=None, date_to=None):
    df = detail_rows(date_from, date_to)
    if df.empty:
        return pd.DataFrame()

    # 엑셀에 존재하는 정산 컬럼만 개인별 누적표에 표시한다.
    # 빨레/보 등 현재 엑셀에서 정산하지 않는 보상은 원본 기록에는 남되 여기서는 제외한다.
    tracked = df[df["settlement_column"] != "__EXCLUDE__"].copy()
    if tracked.empty:
        return pd.DataFrame()

    p = tracked.pivot_table(
        index="member",
        columns="settlement_column",
        values="share_qty",
        aggfunc="sum",
        fill_value=0,
    )
    p["합산가치"] = tracked.groupby("member")["value"].sum()
    p = p.reset_index()

    # 기존 엑셀과 동일한 컬럼 순서. 없는 컬럼도 0으로 만들어 형식을 고정한다.
    excel_order = [
        "파템", "초템", "흰템", "전설픽업", "동료소환",
        "룬 소환", "랜덤 룬", "보라레시피", "파랑레시피", "초록레시피",
    ]
    for col in excel_order:
        if col not in p.columns:
            p[col] = 0.0
    return p[["member"] + excel_order + ["합산가치"]]
