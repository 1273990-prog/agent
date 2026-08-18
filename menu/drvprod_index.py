import sys
import os
import json
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from services.service_factory import ServiceFactory
from common.constants import AgentConstants
from common.utils import AgentUtils

def main():  
    try:
        krx_service = ServiceFactory.create(AgentConstants.KRX)
        if not krx_service:
            print("[오류] KRX 서비스를 초기화할 수 없습니다.")
            return

        config = AgentUtils.load_config("agent_key.json")

        default_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")  

        index_date = input("조회할 기준일자(예: 20260818): ").strip() or default_date

        if not index_date or len(index_date) != 8 or not index_date.isdigit():
            print("[오류] 유효한 기준일자를 입력하세요.")
            return

        index_request = {
            "AUTH_KEY": config.get("krx_auth_key", ""),
            "basDd": index_date
        }

        print(f"[정보] 파생상품지수를 조회 중입니다...")
        result = krx_service.get_drvprod_index_to_json(json.dumps(index_request))
        
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
        print(f"[오류] 지수 조회 중 예외가 발생했습니다: {e}")

if __name__ == "__main__":
    main()