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
        koreaexim_service = ServiceFactory.create(AgentConstants.KOREAEXIM)
        if not koreaexim_service:
            print("[오류] KOREAEXIM 서비스를 초기화할 수 없습니다.")
            return

        config = AgentUtils.load_config("agent_key.json")

        # 통과시킬 코드 목록
        valid_codes = ['AP01', 'AP02', 'AP03']

        data_code = input("조회할 요청코드(예: 환율 AP01): ").strip() or "AP01"

        if not data_code or data_code not in valid_codes:
            print("[오류] 유효한 종목코드를 입력하세요.")
            return

        price_request = {
            "authkey": config.get("koreaexim_authkey", ""),
            "data": data_code
        }

        print(f"[정보] 검색코드 {data_code}의 시세를 조회 중입니다...")
        result = koreaexim_service.get_exchange_price_to_json(json.dumps(price_request))
        
        if isinstance(result, list):
            print("\n" + "-" * 40)
            for item in result:
                print(f" 결과값: {item}")
            print("-" * 40)
        else:
            print("\n" + "-" * 40)
            print(f" 결과값: {result}")
            print("-" * 40)

    except Exception as e:
        print(f"[오류] 검색 중 예외가 발생했습니다: {e}")

if __name__ == "__main__":
    main()