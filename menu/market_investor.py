import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from services.service_factory import ServiceFactory
from common.constants import AgentConstants
from common.utils import AgentUtils

def main():  
    try:
        kis_service = ServiceFactory.create(AgentConstants.KIS)
        if not kis_service:
            print("[오류] KIS 서비스를 초기화할 수 없습니다.")
            return

        config = AgentUtils.load_config("agent_key.json")

        access_token = kis_service.check_valid_token(config)

        print("\n시장별 투자자매매동향 조회를 진행합니다.")
        if not access_token:
            print("▶ 토큰이 발급되지 않아 시장별 투자자매매동향을 조회할 수 없습니다.")
            return

        print("\n조회할 시장구분 코드 KSP: KOSPI, KSQ: KOSDAQ")

        market_type = input().strip() or "KSP"

        print("\n조회할 업종구분 코드 0001: KOSPI, 1001: KOSDAQ")

        index_code = input().strip() or "0001"

        index_request = {
            "access_token": access_token,
            "appkey": config.get("kis_appkey", ""),
            "appsecret": config.get("kis_appsecret", ""),
            "tr_id": "FHPTJ04030000",
            "custtype": "P",
            "fid_input_iscd": market_type,
            "fid_input_iscd_2": index_code
        }

        print(f"[정보] {market_type} {index_code}를 조회 중입니다...")
        result = kis_service.get_market_investor_to_json(json.dumps(index_request))
        
        rt_cd = result.get("rt_cd")
        msg1 = result.get("msg1", "")
        output = result.get("output", {})
        
        if rt_cd == "0" and output:
            print("\n" + "-" * 40)
            print(f" 결과값: {output}")
            print("-" * 40)
        else:
            print(f"\n[실패] API 응답 코드: {rt_cd}, 메시지: {msg1}")
    except Exception as e:
        print(f"[오류] 시장별 투자자매매동향 조회 중 예외가 발생했습니다: {e}")

if __name__ == "__main__":
    main()