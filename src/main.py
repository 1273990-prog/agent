import sys
import os
import json
from typing import Dict, Any, Optional

# Add the 'src' directory (current script's parent directory) to Python search path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from services.service_factory import ServiceFactory
from common.utils import AgentUtils
from common.constants import AgentConstants

def load_config() -> Dict[str, Any]:
    """Loads configuration keys from agent_key.json located in the project root."""
    # Look for agent_key.json in the parent directory of 'src'
    config_path = os.path.abspath(os.path.join(current_dir, '../agent_key.json'))
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[오류] 설정 파일을 읽는데 실패했습니다: {e}")
            return {}
    else:
        print(f"[경고] 설정 파일({config_path})이 존재하지 않습니다.")
        return {}

def show_menu():
    print("\n" + "=" * 45)
    print("        [ KIS 한국투자증권 에이전트 메뉴 ]")
    print("=" * 45)
    print("  1. 국내 주식 실시간 시세 조회")
    print("  2. 국내 주식 지수 조회 (KOSPI/KOSDAQ)")
    print("  3. 프로그램 종료")
    print("=" * 45)

def main():
    config = load_config()
    if not config:
        print("[오류] 설정을 불러올 수 없어 프로그램을 종료합니다.")
        return

    kis_service = ServiceFactory.create(AgentConstants.KIS)
    if not kis_service:
        print("[오류] KIS 서비스를 초기화할 수 없습니다.")
        return

    access_token = None

    show_menu()
    choice = input("원하는 메뉴 번호를 입력하세요: ").strip()

    db_host = config.get("db_host", "")
    port = config.get("port", "")
    database = config.get("database", "")
    username = config.get("username", "")
    password = config.get("password", "")
    appkey = config.get("appkey", "")
    appsecret = config.get("appsecret", "")

    get_data = {
        "net_value": {
            "action": AgentConstants.SELECT,
            "host": db_host,
            "port": port,
            "database": database,
            "username": username,
            "password": password
        },
        "data_value": {
            "query_key": "SELECT_TOKEN_BY_DATE",
            "params": {'svc_type': 'HIS'}
        }
    }

    get_data_json = json.dumps(get_data)

    token_data = kis_service.get_valid_token_to_json(get_data_json)

    if token_data:
        access_token = token_data.get("access_token")
        print("[정보] 데이터베이스에서 기존 유효 토큰을 로드했습니다.")
    else:
        print("[정보] 유효한 토큰이 없거나 만료되었습니다. 새 토큰을 요청합니다...")
        token_request_json = json.dumps({
        "appkey": appkey,
        "appsecret": appsecret
        })

        try:
            token_data = kis_service.get_access_token_to_json(token_request_json)

            access_token = token_data.get("access_token")

            token_data["rule_no"] = AgentUtils.get_rule_no()
            token_data["svc_type"] = "HIS"

            set_data = {
                "net_value": {
                    "action": AgentConstants.INSERT,
                    "host": db_host,
                    "port": port,
                    "database": database,
                    "username": username,
                    "password": password
                },
                "data_value": {
                    "query_key": "INSERT_TOKEN_INFO",
                    "params": token_data
                }
            }

            kis_service.set_valid_token_to_string(json.dumps(set_data))
            print("[정보] 새 토큰을 데이터베이스에 성공적으로 저장했습니다.")
            return access_token
        
        except Exception as e:
            print(f"[오류] 토큰 발급 및 저장 중 문제가 발생했습니다: {e}")
            return None

    if choice == '1':
        print("\n[메뉴 1] 국내 주식 실시간 시세 조회를 진행합니다.")
        if not access_token:
            print("▶ 토큰이 발급되지 않아 시세를 조회할 수 없습니다.")
            return

        stock_code = input("조회할 주식 종목코드(6자리, 예: 삼성전자 005930): ").strip() or "005930"
        if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
            print("[오류] 올바른 6자리 숫자 종목코드를 입력하세요.")
            return

        price_request = {
            "access_token": access_token,
            "appkey": config.get("appkey", ""),
            "appsecret": config.get("appsecret", ""),
            "tr_id": "FHPUP02100000",
            "custtype": "P",
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code
        }

        try:
            print(f"[정보] 종목코드 {stock_code}의 시세를 조회 중입니다...")
            result = kis_service.get_stock_price_to_json(json.dumps(price_request))
            
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
            print(f"[오류] 시세 조회 중 예외가 발생했습니다: {e}")

    elif choice == '2':
        print("\n[메뉴 2] 국내 주식 지수 조회를 진행합니다.")
        if not access_token:
            print("▶ 토큰이 발급되지 않아 지수를 조회할 수 없습니다.")
            return

        iscd = input("조회할 지수 코드 (기본값 0001: KOSPI, 0003: KOSDAQ): ").strip() or "0001"

        index_request = {
            "access_token": access_token,
            "appkey": config.get("appkey", ""),
            "appsecret": config.get("appsecret", ""),
            "tr_id": "FHPUP02100000",
            "custtype": "P",
            "fid_cond_mrkt_div_code": "U",
            "fid_input_iscd": iscd
        }

        try:
            print(f"[정보] 지수 코드 {iscd}를 조회 중입니다...")
            result = kis_service.get_kospi_index_to_json(json.dumps(index_request))
            
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
            print(f"[오류] 지수 조회 중 예외가 발생했습니다: {e}")

    elif choice == '3':
        print("\n프로그램을 종료합니다. 감사합니다.")
        return
    else:
        print("\n[경고] 잘못된 선택입니다. 1~3 사이의 번호를 입력해주세요.")

if __name__ == "__main__":
    main()
