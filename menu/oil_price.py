import sys
import os
import json
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from services.service_factory import ServiceFactory
from common.constants import AgentConstants
from common.utils import AgentUtils

def main():
    try:
        opinet_service = ServiceFactory.create(AgentConstants.OPINET)
        if not opinet_service:
            print("[오류] OPINET 서비스를 초기화할 수 없습니다.")
            return

        config = AgentUtils.load_config("agent_key.json")

        # 통과시킬 코드 목록
        valid_codes = ['B034', 'B027', 'C004', 'D047', 'K105']

        data_code = input("조회할 제품코드(예: 보통휘발유 B027): ").strip() or "B027"

        if not data_code or data_code not in valid_codes:
            print("[오류] 유효한 제품코드를 입력하세요.")
            return

        area_code = input("조회할 지역 구분코드(4자리, 예: 서울금천 0125): ").strip() or "0125"
        if not area_code or not area_code.isdigit():
            print("[오류] 올바른 지역 구분코드를 입력하세요.")
            return

        price_request = {
            "certkey": config.get("opinet_certkey", ""),
            "prodcd": data_code,
            "area": area_code
        }

        print(f"[정보] 검색코드 {data_code}의 시세를 조회 중입니다...")
        result = opinet_service.get_oil_price_to_json(json.dumps(price_request))

        print("\n" + "-" * 40)
        print(f" 결과값: {result}")
        print("-" * 40)

    except Exception as e:
        print(f"[오류] 검색 중 예외가 발생했습니다: {e}")

if __name__ == "__main__":
    main()