import sys
import os
import json
from typing import Dict, Any
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from services.service_factory import ServiceFactory
from common.constants import AgentConstants
from common.utils import AgentUtils

def main():
    try:
        opendart_service = ServiceFactory.create(AgentConstants.OPENDART)
        if not opendart_service:
            print("[오류] OPENDART 서비스를 초기화할 수 없습니다.")
            return

        config = AgentUtils.load_config("agent_key.json")

        # 통과시킬 코드 목록

        corp_code = input("조회할 고유번호(8자리, 예: 삼성전자 00126380): ").strip() or "00126380"
        if not corp_code or len(corp_code) != 8 or not corp_code.isdigit():
            print("[오류] 올바른 8자리 숫자 고유번호를 입력하세요.")
            return

        bsns_year = input("조회할 사업연도(4자리, 예: 2025): ").strip() or str(date.today().year - 1)
        if not bsns_year or len(bsns_year) != 4 or not bsns_year.isdigit():
            print("[오류] 올바른 사업연도를 입력하세요.")
            return
        
        valid_reprt_code = ['11011', '11012', '11013', '11014']  #사업보고서, 반기보고서, 1분기보고서, 3분기보고서

        reprt_code = input("조회할 보고서 코드(예: 사업보고서 11011): ").strip() or "11011"

        if not reprt_code or reprt_code not in valid_reprt_code:
            print("[오류] 유효한 보고서 코드를 입력하세요.")
            return

        valid_fs_div = ['OFS', 'CFS']  #재무제표, 연결재무제표
        
        fs_div = input("조회할 개별/연결구분(예: 연결재무제표 CFS): ").strip() or "CFS"

        if not fs_div or fs_div not in valid_fs_div:
            print("[오류] 유효한 개별/연결구분을 입력하세요.")
            return

        stmt_request = {
            "crtfc_key": config.get("dart_crtfc_key", ""),
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div            
        }

        print(f"[정보] 제무제표를 조회 중입니다...")
        result = opendart_service.get_financial_statements_to_json(json.dumps(stmt_request))

        print("\n" + "-" * 40)
        print(f" 결과값: {result}")
        print("-" * 40)

    except Exception as e:
        print(f"[오류] 검색 중 예외가 발생했습니다: {e}")

if __name__ == "__main__":
    main()