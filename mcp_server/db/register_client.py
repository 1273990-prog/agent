import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth.client_store import ClientStore

if __name__ == '__main__':
    """
    새 MCP 클라이언트를 mcp_clients DB 테이블에 등록하는 유틸리티입니다.
    실행: python register_client.py
    """
    print('=== MCP 클라이언트 등록 ===')
    client_id     = input('client_id 입력: ').strip()
    client_secret = input('client_secret 입력: ').strip()
    name          = input('클라이언트 이름 입력: ').strip()
    scopes_input  = input('허용 scopes 입력 (공백 구분, 예: stock:read exchange:read): ').strip()
    scopes        = scopes_input.split()

    try:
        result = ClientStore.register(client_id, client_secret, name, scopes)
        print(f'\n[완료] 클라이언트 "{result["name"]}" ({result["client_id"]}) 가 DB에 등록되었습니다.')
        print(f'       허용 scopes: {result["scopes"]}')
        print(f'       등록 일시:   {result["created_at"]}')
    except ValueError as e:
        print(f'\n[오류] {e}')
        sys.exit(1)