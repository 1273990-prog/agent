import sys
import os
import json
from typing import Dict, Any, List, Union

# 기존 src 경로를 Python 경로에 추가 (기존 코드 변경 없이 재사용)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from services.service_factory import ServiceFactory
from common.constants import AgentConstants
from common.utils import AgentUtils

# 허용된 data_code 목록
VALID_DATA_CODES = ['AP01', 'AP02', 'AP03']


def get_exchange_price(data_code: str = 'AP01') -> Union[List[Dict], Dict[str, Any]]:
    """
    환율 정보를 조회합니다.
    기존 menu/exchange_price.py 의 로직을 MCP Tool 용 함수로 래핑합니다.

    Args:
        data_code: 조회 코드 (AP01: 환율, AP02: 대고객환율, AP03: 재정환율)

    Returns:
        KOREAEXIM API 응답 (리스트 또는 딕셔너리)
    """
    if data_code not in VALID_DATA_CODES:
        raise ValueError(
            f'유효하지 않은 data_code: {data_code}. '
            f'허용값: {", ".join(VALID_DATA_CODES)}'
        )

    koreaexim_service = ServiceFactory.create(AgentConstants.KOREAEXIM)
    if not koreaexim_service:
        raise RuntimeError('[오류] KOREAEXIM 서비스를 초기화할 수 없습니다.')

    config = AgentUtils.load_config('agent_key.json')

    price_request = {
        'authkey': config.get('koreaexim_authkey', ''),
        'data': data_code
    }

    return koreaexim_service.get_exchange_price_to_json(json.dumps(price_request))
