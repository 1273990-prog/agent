import sys
import os
import json
from typing import Dict, Any

# 기존 src 경로를 Python 경로에 추가 (기존 코드 변경 없이 재사용)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from services.service_factory import ServiceFactory
from common.constants import AgentConstants
from common.utils import AgentUtils

# 허용된 제품코드 목록
VALID_PROD_CODES = ['B034', 'B027', 'C004', 'D047', 'K105']
PROD_CODE_NAMES = {
    'B034': '고급휘발유',
    'B027': '보통휘발유',
    'C004': '경유',
    'D047': '등유',
    'K105': 'LPG(부탄)'
}


def get_oil_price(prod_code: str, area_code: str) -> Dict[str, Any]:
    """
    지역별 유가 정보를 조회합니다.
    기존 menu/oil_price.py 의 로직을 MCP Tool 용 함수로 래핑합니다.

    Args:
        prod_code: 제품코드
            B034: 고급휘발유
            B027: 보통휘발유
            C004: 경유
            D047: 등유
            K105: LPG(부탄)
        area_code: 지역 구분코드 4자리 (예: 서울금천 0125)

    Returns:
        OPINET API 응답 딕셔너리
    """
    if prod_code not in VALID_PROD_CODES:
        raise ValueError(
            f'유효하지 않은 prod_code: {prod_code}. '
            f'허용값: {", ".join(VALID_PROD_CODES)}'
        )

    if not area_code or not area_code.isdigit():
        raise ValueError(f'올바른 숫자 지역 구분코드를 입력하세요. 입력값: {area_code}')

    opinet_service = ServiceFactory.create(AgentConstants.OPINET)
    if not opinet_service:
        raise RuntimeError('[오류] OPINET 서비스를 초기화할 수 없습니다.')

    config = AgentUtils.load_config('agent_key.json')

    price_request = {
        'certkey': config.get('opinet_certkey', ''),
        'prodcd': prod_code,
        'area': area_code
    }

    return opinet_service.get_oil_price_to_json(json.dumps(price_request))
