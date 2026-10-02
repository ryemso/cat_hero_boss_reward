from __future__ import annotations
from pathlib import Path
from datetime import date, datetime
import shutil
import uuid
import hashlib
import sqlite3
import pandas as pd
import streamlit as st
from PIL import Image

from core import db
from core.recognition import recognize_card
from core.vision import pil_to_bgr, bgr_to_pil, detect_reward_cards, match_reward, read_quantity
from core.settlement import member_summary, member_item_pivot, detail_rows
from core.exporter import build_xlsx

ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "data" / "templates"
STARTER_DIR = ROOT / "data" / "starter_templates"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="보스 정산 v1", page_icon="🎮", layout="wide")
db.init_db()

@st.cache_data(show_spinner=False)
def load_starter_names():
    return sorted([p.name for p in STARTER_DIR.glob("*.png")])


def get_templates():
    return db.get_templates()


def reward_options():
    rows = db.rows("SELECT id,name FROM reward_master WHERE enabled=1 ORDER BY name")
    return {r["name"]: r["id"] for r in rows}


def members_dict():
    return {r["name"]: r["id"] for r in db.rows("SELECT id,name FROM members WHERE active=1 ORDER BY id")}


def bosses_dict():
    return {r["name"]: r["id"] for r in db.rows("SELECT id,name FROM bosses WHERE active=1 ORDER BY id")}

st.title("🎮 보스 정산 반자동화 v1")
st.caption("스크린샷 → 카드 인식 → 숫자 OCR → 사람 확인 → 자동 분배 → 정산 → Excel")
st.info("엑셀 기준 매핑 적용: 픽뽑/픽업 → 전설픽업, 룬 → 룬 소환, 동 → 동료소환, 룬뽑 → 랜덤 룬. 빨레/보도 정산에 포함하며, 보상 마스터에서 값어치를 설정할 수 있습니다.")

tabs = st.tabs(["📷 보스전 등록", "📒 개인 장부", "💰 전체 정산", "🕘 기록", "🧩 보상 마스터", "⚙️ 설정", "📤 Excel"])

with tabs[0]:
    st.subheader("보스전 등록")
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        raid_date = st.date_input("날짜", value=date.today())
    with c2:
        raid_time = st.time_input("시간", value=datetime.now().time().replace(second=0, microsecond=0))
    with c3:
        bosses = bosses_dict()
        boss_name = st.selectbox("보스", list(bosses.keys()) if bosses else ["미등록"])

    mems = members_dict()
    selected_members = st.multiselect("참여자", list(mems.keys()), default=list(mems.keys())[:3])
    st.caption(f"자동 인원수: {len(selected_members)}명")

    uploaded = st.file_uploader("처치 결과 스크린샷", type=["png","jpg","jpeg"], key="raidshot")
    detected_rows = []
    upload_sig = hashlib.sha256(uploaded.getvalue()).hexdigest() if uploaded else None
    if st.button('다시 인식', disabled=uploaded is None):
        st.session_state.pop('recognition_sig', None)
        st.session_state.pop('last_raid_upload_sig', None)
        st.session_state.pop('raid_table', None)
    templates = get_templates()
    readable = [t for t in templates if Path(t['template_path']).is_file()]
    if len(readable) != len(templates) or not templates:
        st.warning(f'템플릿 경로 확인 필요: 등록 {len(templates)}개 / 파일 {len(readable)}개')
    if uploaded:
        pil = Image.open(uploaded)
        st.image(pil, caption="입력 이미지", width=320)
        img = pil_to_bgr(pil)
        cards = detect_reward_cards(img)
        st.write(f"보상 카드 감지: **{len(cards)}개**")
        threshold = float(db.setting("match_threshold", 0.78))
        st.caption(f"템플릿 {len(readable)}개 연결 / 자동매칭 기준 {threshold:.2f}")
        if st.session_state.get('recognition_sig') != upload_sig:
            with st.spinner('보상 매칭 및 수량 인식 중...'):
                st.session_state.recognition_rows = [recognize_card(card, templates, threshold) for card in cards]
            st.session_state.recognition_sig = upload_sig
        detected_rows = st.session_state.recognition_rows
        cols = st.columns(min(max(len(cards),1), 5)) if cards else []
        for i, card in enumerate(cards):
            with cols[i % len(cols)]:
                st.image(bgr_to_pil(card.crop), caption=f"#{i+1} {card.rarity}", use_container_width=True)

    rewards = reward_options()
    reward_names = list(rewards.keys())
    if "raid_editor" not in st.session_state or st.session_state.get("last_raid_upload_sig") != upload_sig:
        st.session_state.pop('raid_table', None)
        st.session_state.raid_editor = pd.DataFrame(detected_rows) if detected_rows else pd.DataFrame([
            {"보상": reward_names[0] if reward_names else "미지정", "수량": 1.0, "OCR수량": None, "인식점수": None, "수량신뢰도": None, "후보ID": "", "등급": ""}
        ])
        st.session_state.last_raid_upload_sig = upload_sig

    st.markdown("#### 인식 결과 확인/수정")
    editor_df = st.session_state.raid_editor.copy()
    if "reward_id" in editor_df.columns:
        editor_df = editor_df.drop(columns=["reward_id"])
    edited = st.data_editor(
        editor_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "보상": st.column_config.SelectboxColumn("보상", options=sorted(set(reward_names + editor_df["보상"].dropna().tolist())) + (["미지정"] if "미지정" not in reward_names else []), required=True),
            "수량": st.column_config.NumberColumn("수량", min_value=0.0, step=1.0, required=True),
            "OCR수량": st.column_config.NumberColumn("OCR수량", disabled=True),
            "인식점수": st.column_config.NumberColumn("인식점수", format="%.3f", disabled=True),
            "수량신뢰도": st.column_config.NumberColumn("수량신뢰도", format="%.3f", disabled=True),
            "후보ID": st.column_config.TextColumn("후보ID", disabled=True),
            "등급": st.column_config.TextColumn("등급", disabled=True),
            "후보보상": st.column_config.TextColumn(disabled=True),
            "매칭상태": st.column_config.TextColumn(disabled=True),
            "수량상태": st.column_config.TextColumn(disabled=True),
        },
        key="raid_table",
    )
    memo = st.text_input("메모", placeholder="선택 사항")
    if st.button("✅ 정산 등록", type="primary", use_container_width=True):
        if not selected_members:
            st.error("참여자를 1명 이상 선택해 주세요.")
        elif edited.empty:
            st.error("보상을 1개 이상 입력해 주세요.")
        elif any(str(x) not in rewards for x in edited["보상"].tolist()):
            st.error("미지정/비활성 보상을 활성 보상으로 바꿔 주세요.")
        elif edited['수량'].isna().any() or (pd.to_numeric(edited['수량'], errors='coerce').fillna(-1) < 0).any():
            st.error('모든 수량을 0 이상의 숫자로 입력해 주세요.')
        else:
            payload=[]
            for _, r in edited.iterrows():
                name=str(r["보상"])
                payload.append({
                    "reward_id": rewards.get(name),
                    "reward_name": name,
                    "quantity": float(r["수량"]),
                    "candidate_id": None if pd.isna(r.get('후보ID')) else r.get('후보ID'),
                    "quantity_confidence": None if pd.isna(r.get('수량신뢰도')) else r.get('수량신뢰도'),
                    "rarity": None if pd.isna(r.get('등급')) else r.get('등급'),
                    "ocr_quantity": None if pd.isna(r.get("OCR수량")) else float(r.get("OCR수량")),
                    "score": None if pd.isna(r.get("인식점수")) else float(r.get("인식점수")),
                })
            raid_id = db.save_raid(
                raid_date, raid_time.strftime("%H:%M"), bosses.get(boss_name),
                [mems[n] for n in selected_members], payload, memo, uploaded.name if uploaded else None
            )
            st.success(f"Raid #{raid_id} 저장 완료. 개인 장부와 전체 정산에 즉시 반영됐습니다.")
            st.session_state.pop("raid_editor", None)
            st.session_state.pop("last_raid_upload_sig", None)

with tabs[1]:
    st.subheader("개인 장부")
    d1, d2 = st.columns(2)
    with d1: f = st.date_input("시작일", value=date.today().replace(day=1), key="ledger_from")
    with d2: t = st.date_input("종료일", value=date.today(), key="ledger_to")
    pivot = member_item_pivot(f, t)
    if pivot.empty:
        st.info("해당 기간의 정산 데이터가 없습니다.")
    else:
        st.dataframe(pivot, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("전체 정산")
    d1, d2 = st.columns(2)
    with d1: f2 = st.date_input("시작일", value=date.today().replace(day=1), key="sum_from")
    with d2: t2 = st.date_input("종료일", value=date.today(), key="sum_to")
    s = member_summary(f2, t2)
    if s.empty:
        st.info("해당 기간의 정산 데이터가 없습니다.")
    else:
        show = s.rename(columns={"member":"사용자","total_value":"보라가치","cash":"현금","after_fee":"수수료 제외"})
        st.dataframe(show, use_container_width=True, hide_index=True,
                     column_config={"보라가치": st.column_config.NumberColumn(format="%.4f"),
                                    "현금": st.column_config.NumberColumn(format="%.2f"),
                                    "수수료 제외": st.column_config.NumberColumn(format="%.2f")})

with tabs[3]:
    st.subheader("보스전 기록")
    raids = db.rows("""
        SELECT r.id, r.raid_date 날짜, r.raid_time 시간, COALESCE(b.name,'') 보스,
               COALESCE(r.memo,'') 메모,
               GROUP_CONCAT(m.name, ', ') 참여자
        FROM raids r LEFT JOIN bosses b ON b.id=r.boss_id
        LEFT JOIN raid_members x ON x.raid_id=r.id
        LEFT JOIN members m ON m.id=x.member_id
        GROUP BY r.id ORDER BY r.raid_date DESC, r.raid_time DESC, r.id DESC
    """)
    rdf = pd.DataFrame(raids)
    if rdf.empty:
        st.info("아직 등록된 보스전이 없습니다.")
    else:
        st.dataframe(rdf, use_container_width=True, hide_index=True)
        rid = st.selectbox("삭제할 Raid ID", [r["id"] for r in raids])
        if st.button("🗑️ 선택 Raid 삭제"):
            db.delete_raid(rid)
            st.success(f"Raid #{rid} 삭제 완료. 누적값은 원본에서 다시 계산되므로 별도 복구 계산이 필요 없습니다.")
            st.rerun()

with tabs[4]:
    st.subheader("보상 마스터")
    st.write("U01~U33은 기존 엑셀 컬럼 기준으로 기본 등록되어 있습니다. 픽뽑/픽업은 모두 전설픽업으로 합산되며, 빨레/보는 인식·기록만 하고 정산 합계에서는 제외됩니다.")
    seeded = pd.DataFrame(db.rows("""
        SELECT rt.candidate_id 후보ID, rm.name 보상명, rm.settlement_column 정산컬럼,
               rm.quantity_mode 수량방식
        FROM reward_templates rt JOIN reward_master rm ON rm.id=rt.reward_id
        ORDER BY rt.candidate_id
    """))
    if not seeded.empty:
        st.dataframe(seeded, use_container_width=True, hide_index=True)

    source_mode = st.radio("템플릿 소스", ["내 이미지에서 카드 추출", "제공된 스타터 후보 사용"], horizontal=True)
    candidate_crops=[]
    if source_mode == "내 이미지에서 카드 추출":
        master_upload = st.file_uploader("'획득 가능 보상' 또는 처치 화면 업로드", type=["png","jpg","jpeg"], key="mastershot")
        if master_upload:
            mpil=Image.open(master_upload)
            mimg=pil_to_bgr(mpil)
            mcards=detect_reward_cards(mimg)
            candidate_crops=[c.crop for c in mcards]
            st.success(f"카드 {len(candidate_crops)}개 감지")
    else:
        starter_names=load_starter_names()
        selected=st.selectbox("스타터 후보", starter_names if starter_names else ["없음"])
        if starter_names:
            import cv2
            from core.vision import load_template
            crop=load_template(STARTER_DIR/selected)
            candidate_crops=[crop]

    if candidate_crops:
        idx = st.number_input("등록할 카드 번호", 1, len(candidate_crops), 1)
        crop = candidate_crops[int(idx)-1]
        st.image(bgr_to_pil(crop), width=120)
        with st.form("master_form", clear_on_submit=True):
            name = st.text_input("보상명", placeholder="예: 초템")
            settlement_col = st.text_input("정산 컬럼", placeholder="예: 초템")
            rarity = st.selectbox("등급", ["AUTO","RED","PURPLE","BLUE","GREEN","YELLOW","GRAY","UNKNOWN"])
            quantity_mode = st.selectbox("수량 방식", ["AUTO","OCR","DEFAULT_ONE"])
            dist = st.selectbox("분배 방식", ["EQUAL","PER_PERSON"])
            unit_value = st.number_input("1단위당 보라가치", min_value=0.0, value=0.0, step=1.0)
            submitted = st.form_submit_button("보상 템플릿 등록", type="primary")
        if submitted:
            if not name.strip():
                st.error("보상명을 입력해 주세요.")
            else:
                import cv2
                filename=f"{uuid.uuid4().hex}.png"
                target=TEMPLATE_DIR/filename
                target.write_bytes(cv2.imencode('.png', crop)[1].tobytes())
                rar = rarity if rarity != "AUTO" else "UNKNOWN"
                try:
                    reward_id = db.execute("""
                        INSERT INTO reward_master(name,settlement_column,rarity,template_path,quantity_mode,distribution_type,unit_value,created_at)
                        VALUES(?,?,?,?,?,?,?,?)
                    """, (name.strip(), settlement_col.strip() or name.strip(), rar, target.relative_to(ROOT).as_posix(), quantity_mode, dist, float(unit_value), datetime.now().isoformat(timespec="seconds")))
                    db.execute("""
                        INSERT OR IGNORE INTO reward_templates(reward_id,candidate_id,template_path,created_at)
                        VALUES(?,?,?,?)
                    """, (reward_id, None, target.relative_to(ROOT).as_posix(), datetime.now().isoformat(timespec="seconds")))
                    st.success(f"'{name}' 등록 완료")
                    st.rerun()
                except Exception as e:
                    st.error(f"등록 실패: {e}")

    st.markdown("#### 현재 보상 마스터")
    master = pd.DataFrame(db.rows("SELECT id,name,settlement_column,rarity,quantity_mode,distribution_type,unit_value,enabled FROM reward_master ORDER BY id"))
    if master.empty:
        st.info("아직 등록된 보상 템플릿이 없습니다. 스타터 후보 U01~을 하나씩 실제 보상명에 연결해 주세요.")
    else:
        st.dataframe(master, use_container_width=True, hide_index=True)
        selected_id = st.selectbox('수정할 보상', master['id'].tolist(),
            format_func=lambda rid: master.set_index('id').loc[rid, 'name'])
        row = master.set_index('id').loc[selected_id]
        st.caption('비활성 보상도 이미지 후보로 인식됩니다. 신규 정산 등록에서는 선택할 수 없습니다. 값어치 수정은 기존 기록의 합계에도 반영됩니다.')
        with st.form(f'reward_edit_{selected_id}'):
            edit_name = st.text_input('보상명 수정', value=row['name'])
            edit_col = st.text_input('정산 컬럼 수정', value=row['settlement_column'], disabled=True)
            rarities = ['UNKNOWN','RED','PURPLE','BLUE','GREEN','YELLOW','GRAY']
            edit_rarity = st.selectbox('등급 수정', rarities, index=rarities.index(row['rarity']) if row['rarity'] in rarities else 0)
            modes = ['AUTO','OCR','DEFAULT_ONE']
            edit_mode = st.selectbox('수량 방식 수정', modes, index=modes.index(row['quantity_mode']))
            distributions = ['EQUAL','PER_PERSON']
            edit_dist = st.selectbox('분배 방식 수정', distributions, index=distributions.index(row['distribution_type']))
            edit_value = st.number_input('값어치 수정 (1단위당 보라가치)', min_value=0.0, value=float(row['unit_value']))
            edit_enabled = st.checkbox('보상 활성', value=bool(row['enabled']))
            if st.form_submit_button('보상 변경 저장'):
                try:
                    db.update_reward(selected_id,edit_name,edit_col,edit_rarity,edit_mode,edit_dist,edit_value,edit_enabled)
                    st.rerun()
                except (ValueError, sqlite3.IntegrityError) as exc:
                    st.error(str(exc))

with tabs[5]:
    st.subheader("설정")
    st.markdown("#### 참여자 / 보스")
    c1,c2=st.columns(2)
    with c1:
        new_member=st.text_input("새 참여자")
        if st.button("참여자 추가") and new_member.strip():
            try:
                db.save_member(None, new_member)
                st.rerun()
            except (ValueError, sqlite3.IntegrityError) as exc:
                st.error(f'참여자 추가 실패: {exc}')
        all_members = db.rows('SELECT * FROM members ORDER BY id')
        st.dataframe(pd.DataFrame(all_members), hide_index=True)
        if all_members:
            selected_mid = st.selectbox('수정할 참여자', [r['id'] for r in all_members],
                format_func=lambda mid: next(r['name'] for r in all_members if r['id']==mid))
            member = next(r for r in all_members if r['id']==selected_mid)
            with st.form(f'member_edit_{selected_mid}'):
                updated_name = st.text_input('참여자 이름 수정', value=member['name'])
                active = st.checkbox('참여자 활성', value=bool(member['active']))
                if st.form_submit_button('참여자 변경 저장'):
                    try:
                        db.save_member(selected_mid, updated_name, active)
                        st.rerun()
                    except (ValueError, sqlite3.IntegrityError) as exc:
                        st.error(str(exc))
            st.caption('정산 기록이 있는 참여자는 비활성화로 관리합니다. 기록이 없는 참여자만 영구 삭제할 수 있습니다.')
            confirmed_delete = st.checkbox('선택 참여자를 영구 삭제', key=f'delete_member_{selected_mid}')
            if st.button('참여자 삭제', disabled=not confirmed_delete):
                try:
                    db.delete_member(selected_mid)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    with c2:
        new_boss=st.text_input("새 보스")
        if st.button("보스 추가") and new_boss.strip():
            db.execute("INSERT OR IGNORE INTO bosses(name) VALUES(?)", (new_boss.strip(),))
            st.rerun()
    st.markdown("#### 환산 / 인식")
    cash100=st.number_input("보라가치 100당 현금", min_value=0.0, value=float(db.setting("cash_per_100_value",500)), step=10.0)
    fee=st.number_input("수수료율", min_value=0.0, max_value=1.0, value=float(db.setting("fee_rate",0.10)), step=0.01, format="%.2f")
    match=st.slider("아이콘 자동매칭 임계값", 0.50, 0.99, float(db.setting("match_threshold",0.78)), 0.01)
    if st.button("설정 저장"):
        db.set_setting("cash_per_100_value", cash100)
        db.set_setting("fee_rate", fee)
        db.set_setting("match_threshold", match)
        st.success("저장했습니다.")

with tabs[6]:
    st.subheader("Excel 내보내기")
    c1,c2=st.columns(2)
    with c1: ef=st.date_input("시작일", value=date.today().replace(day=1), key="exp_from")
    with c2: et=st.date_input("종료일", value=date.today(), key="exp_to")
    xbytes=build_xlsx(ef,et)
    st.download_button(
        "📥 정산 Excel 다운로드",
        data=xbytes,
        file_name=f"보스정산_{ef}_{et}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
