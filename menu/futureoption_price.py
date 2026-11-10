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

        print("\n국내 선물옵션 실시간 시세 조회를 진행합니다.")

        if not access_token:
            print("▶ 토큰이 발급되지 않아 시세를 조회할 수 없습니다.")
            return

        stock_code = input("조회할 선물옵션 종목코드(5자리, 예: KOSPI 200 10100): ").strip() or "10100"
        if not stock_code or len(stock_code) != 5 or not stock_code.isdigit():
            print("[오류] 올바른 5자리 숫자 종목코드를 입력하세요.")
            return

        price_request = {
            "access_token": access_token,
            "appkey": config.get("kis_appkey", ""),
            "appsecret": config.get("kis_appsecret", ""),
            "tr_id": "FHMIF10000000",
            "fid_cond_mrkt_div_code": "F",
            "fid_input_iscd": stock_code
        }

        print(f"[정보] 종목코드 {stock_code}의 시세를 조회 중입니다...")
        result = kis_service.get_futureoption_price_to_json(json.dumps(price_request))
        
        rt_cd = result.get("rt_cd")
        msg1 = result.get("msg1", "")

        # 'output'으로 시작하는 모든 키(output, output1, output2, output3 등)를 동적 수집                                                                                             
        outputs = {                                                                                                                                                                   
            k: v for k, v in result.items()                                                                                                                                           
            if k.startswith("output") and v                                                                                                                                           
        }                                                                                                                                                                             
                                                                                                                                                                                        
        if rt_cd == "0" and outputs:                                                                                                                                                  
            print("\n" + "-" * 40)                                                                                                                                                    
            # 단일 'output'만 있는 기존 API 응답 구조도 호환 지원                                                                                                                     
            if len(outputs) == 1 and "output" in outputs:                                                                                                                             
                val = outputs["output"]                                                                                                                                               
                if isinstance(val, list):                                                                                                                                             
                    for item in val:                                                                                                                                                  
                        print(f" 결과값: {item}")                                                                                                                                     
                else:                                                                                                                                                                 
                    print(f" 결과값: {val}")                                                                                                                                          
            else:                                                                                                                                                                     
                # output1, output2, output3, output4 ... 동적 순회 출력                                                                                                               
                for key in sorted(outputs.keys()):                                                                                                                                    
                    val = outputs[key]                                                                                                                                                
                    if isinstance(val, list):                                                                                                                                         
                        print(f" [{key}]")                                                                                                                                            
                        for item in val:                                                                                                                                              
                            print(f"   - {item}")                                                                                                                                     
                    else:                                                                                                                                                             
                        print(f" [{key}] 결과값: {val}")                                                                                                                              
            print("-" * 40)                                                                                                                                                           
        else:                                                                                                                                                                         
            print(f"\n[실패] API 응답 코드: {rt_cd}, 메시지: {msg1}")

    except Exception as e:
        print(f"[오류] 지수 조회 중 예외가 발생했습니다: {e}")

if __name__ == "__main__":
    main()