"""Recognition payload shared by UI and regression tests."""
from .vision import match_reward, read_quantity


def recognize_card(card, templates, threshold, quantity_reader=None):
    matched = match_reward(card.crop, templates, threshold)
    accepted = bool(matched and matched['accepted'])
    mode = matched.get('quantity_mode', 'AUTO') if accepted else 'AUTO'
    enabled = bool(matched.get('enabled', 1)) if matched else True
    if mode == 'DEFAULT_ONE':
        raw, confidence = None, None
        quantity, status = 1, '기본 1개 (OCR 미사용)'
    else:
        raw, confidence = (quantity_reader or read_quantity)(card.crop, default_one=False)
        quantity = raw if raw is not None else 1
        status = 'OCR 인식' if raw is not None else 'OCR 실패: 수량 확인 필요'
    name = matched['name'] if accepted else '미지정'
    return {
        'reward_id': matched['id'] if accepted else None,
        '보상': name, '수량': quantity, 'OCR수량': raw,
        '인식점수': round(matched['score'], 3) if matched else None,
        '수량신뢰도': round(confidence, 3) if confidence is not None else None,
        '후보ID': (matched.get('candidate_id') or '') if matched else '',
        '후보보상': matched['name'] if matched else '',
        '등급': card.rarity,
        '매칭상태': ('자동매칭' if enabled else '비활성 보상: 교체 필요') if accepted else
                       ('낮은 점수: 보상 확인 필요' if matched else '템플릿 없음/경로 오류'),
        '수량상태': status,
    }
