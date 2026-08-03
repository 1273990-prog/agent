import json
import hashlib
import os
import sys
from typing import Optional, Dict, Any, List

# 기존 src 경로 추가 — DbConn, AgentUtils 재사용 (기존 코드 변경 없음)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from common.db_conn import DbConn
from common.utils import AgentUtils

# 허용 가능한 scope 목록
VALID_SCOPES = ['stock:read', 'index:read', 'exchange:read', 'oil:read']


def _get_net_value(action: str) -> str:
    """
    agent_key.json 에서 DB 접속 정보를 읽어
    DbConn 이 요구하는 net_value JSON 문자열을 반환합니다.
    기존 kis_service.py 의 check_valid_token 패턴과 동일합니다.
    """
    config = AgentUtils.load_config('agent_key.json')
    net_value = {
        'action':   action,
        'host':     config.get('db_host', ''),
        'port':     config.get('port', 5432),
        'database': config.get('database', ''),
        'username': config.get('username', ''),
        'password': config.get('password', '')
    }
    return json.dumps(net_value)


def _hash_secret(secret: str) -> str:
    """client_secret 을 SHA-256 해시로 변환합니다."""
    return hashlib.sha256(secret.encode()).hexdigest()


class ClientStore:

    @staticmethod
    def verify(client_id: str, client_secret: str) -> Optional[Dict[str, Any]]:
        """
        client_id + client_secret 을 검증합니다.
        일치하면 클라이언트 정보를 반환하고, 불일치하면 None 을 반환합니다.

        기존 DbConn 패턴:
            DbConn(net_value_json)
            → create_request(data_value_json)
            → create_response()
        """
        try:
            db = DbConn(_get_net_value('SELECT'))
            db.create_request(json.dumps({
                'query_key': 'SELECT_CLIENT_BY_ID',
                'params': {'client_id': client_id}
            }))
            result = json.loads(db.create_response())

            # 결과 없음
            if not result or result == [{}]:
                return None

            client = result[0]

            # client_secret 해시 비교
            if client.get('client_secret_hash') != _hash_secret(client_secret):
                return None

            return client

        except Exception as e:
            print(f'[오류] ClientStore.verify 실패: {e}')
            return None

    @staticmethod
    def get(client_id: str) -> Optional[Dict[str, Any]]:
        """
        client_id 로 단일 클라이언트를 조회합니다.
        client_secret_hash 는 제외하고 반환합니다.
        """
        try:
            db = DbConn(_get_net_value('SELECT'))
            db.create_request(json.dumps({
                'query_key': 'SELECT_CLIENT_BY_ID',
                'params': {'client_id': client_id}
            }))
            result = json.loads(db.create_response())

            if not result or result == [{}]:
                return None

            client = dict(result[0])
            client.pop('client_secret_hash', None)  # 해시 노출 방지
            return client

        except Exception as e:
            print(f'[오류] ClientStore.get 실패: {e}')
            return None

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        """
        등록된 모든 클라이언트 목록을 반환합니다.
        client_secret_hash 는 제외하고 반환합니다.
        """
        try:
            db = DbConn(_get_net_value('SELECT'))
            db.create_request(json.dumps({
                'query_key': 'SELECT_ALL_CLIENTS',
                'params': {}
            }))
            result = json.loads(db.create_response())

            if not result or result == [{}]:
                return []

            return result  # SELECT_ALL_CLIENTS 는 hash 컬럼 미포함

        except Exception as e:
            print(f'[오류] ClientStore.list_all 실패: {e}')
            return []

    @staticmethod
    def register(
        client_id: str,
        client_secret: str,
        name: str,
        scopes: List[str]
    ) -> Dict[str, Any]:
        """
        새 클라이언트를 mcp_clients 테이블에 등록합니다.

        Args:
            client_id     : 고유 클라이언트 ID
            client_secret : 평문 시크릿 (내부에서 해시 처리 후 저장)
            name          : 클라이언트 이름
            scopes        : 허용할 scope 목록

        Returns:
            등록된 클라이언트 정보 (client_secret_hash 제외)

        Raises:
            ValueError: client_id 중복 또는 유효하지 않은 scope
        """
        # client_id 중복 확인
        if ClientStore.get(client_id):
            raise ValueError(f'이미 존재하는 client_id 입니다: {client_id}')

        # scope 유효성 확인
        invalid_scopes = [s for s in scopes if s not in VALID_SCOPES]
        if invalid_scopes:
            raise ValueError(
                f'유효하지 않은 scope: {invalid_scopes}. '
                f'허용값: {VALID_SCOPES}'
            )

        db = DbConn(_get_net_value('INSERT'))
        db.create_request(json.dumps({
            'query_key': 'INSERT_CLIENT',
            'params': {
                'client_id':          client_id,
                'client_secret_hash': _hash_secret(client_secret),
                'name':               name,
                'scopes':             scopes
            }
        }))
        db.create_response()

        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc).isoformat()
        return {'client_id': client_id, 'name': name, 'scopes': scopes, 'created_at': created_at}

    @staticmethod
    def delete(client_id: str) -> bool:
        """
        client_id 에 해당하는 클라이언트를 삭제합니다.

        Returns:
            True: 삭제 성공 / False: 해당 client_id 없음
        """
        db = DbConn(_get_net_value('DELETE'))
        db.create_request(json.dumps({
            'query_key': 'DELETE_CLIENT_BY_ID',
            'params': {'client_id': client_id}
        }))
        result = json.loads(db.create_response())
        return result.get('affected_rows', 0) > 0
