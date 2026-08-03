import sys
import os
import json
from typing import Dict, Any

# 기존 src 경로를 Python 경로에 추가 (기존 코드 변경 없이 재사용)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from services.service_factory import ServiceFactory
from common.constants import AgentConstants
from common.utils import AgentUtils


def _get_kis_service_and_token():
    """KIS 서비스 인스턴스와 유효 토큰을 반환하는 내부 헬퍼 함수입니다."""
    kis_service = ServiceFactory.create(AgentConstants.KIS)
    if not kis_service:
        raise RuntimeError('[오류] KIS 서비스를 초기화할 수 없습니다.')

    config = AgentUtils.load_config('agent_key.json')
    access_token = kis_service.check_valid_token(config)

    if not access_token:
        raise RuntimeError('[오류] KIS 액세스 토큰을 발급받을 수 없습니다.')

    return kis_service, config, access_token


def get_stock_price(stock_code: str) -> Dict[str, Any]:
    """
    국내 주식 실시간 시세를 조회합니다.
    기존 menu/stock_price.py 의 로직을 MCP Tool 용 함수로 래핑합니다.

    Args:
        stock_code: 6자리 종목코드 (예: 삼성전자 005930)

    Returns:
        KIS API 응답 딕셔너리
    """
    if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
        raise ValueError(f'올바른 6자리 숫자 종목코드를 입력하세요. 입력값: {stock_code}')

    kis_service, config, access_token = _get_kis_service_and_token()

    price_request = {
        'access_token': access_token,
        'appkey': config.get('kis_appkey', ''),
        'appsecret': config.get('kis_appsecret', ''),
        'tr_id': 'FHKST01010100',
        'fid_cond_mrkt_div_code': 'J',
        'fid_input_iscd': stock_code
    }

    return kis_service.get_stock_price_to_json(json.dumps(price_request))


def get_kospi_index() -> Dict[str, Any]:
    """
    KOSPI 지수를 조회합니다.
    기존 menu/kospi_index.py 의 로직을 MCP Tool 용 함수로 래핑합니다.

    Returns:
        KIS API 응답 딕셔너리
    """
    kis_service, config, access_token = _get_kis_service_and_token()

    index_request = {
        'access_token': access_token,
        'appkey': config.get('kis_appkey', ''),
        'appsecret': config.get('kis_appsecret', ''),
        'tr_id': 'FHPUP02100000',
        'custtype': 'P',
        'fid_cond_mrkt_div_code': 'U',
        'fid_input_iscd': '0001'
    }

    return kis_service.get_kospi_index_to_json(json.dumps(index_request))


def get_kosdaq_index() -> Dict[str, Any]:
    """
    KOSDAQ 지수를 조회합니다.
    기존 menu/kosdaq_index.py 의 로직을 MCP Tool 용 함수로 래핑합니다.

    Returns:
        KIS API 응답 딕셔너리
    """
    kis_service, config, access_token = _get_kis_service_and_token()

    index_request = {
        'access_token': access_token,
        'appkey': config.get('kis_appkey', ''),
        'appsecret': config.get('kis_appsecret', ''),
        'tr_id': 'FHPUP02100000',
        'custtype': 'P',
        'fid_cond_mrkt_div_code': 'U',
        'fid_input_iscd': '1001'
    }

    return kis_service.get_kospi_index_to_json(json.dumps(index_request))
