import jwt
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

# .env 또는 환경변수에서 시크릿 로드
JWT_SECRET: str = os.getenv('JWT_SECRET', 'bizbox-mcp-secret-change-in-production')
JWT_ALGORITHM: str = 'HS256'
JWT_EXPIRE_HOURS: int = int(os.getenv('JWT_EXPIRE_HOURS', '1'))


class TokenManager:

    @staticmethod
    def create_token(client_id: str, scopes: list) -> str:
        """
        Client Credentials 용 Access Token(JWT)을 생성합니다.
        sub: client_id
        scopes: 허용된 권한 목록
        """
        now = datetime.now(timezone.utc)
        payload: Dict[str, Any] = {
            'sub': client_id,
            'scopes': scopes,
            'iat': now,
            'exp': now + timedelta(hours=JWT_EXPIRE_HOURS)
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """
        JWT 토큰을 검증하고 payload 를 반환합니다.
        만료 또는 유효하지 않은 경우 예외를 발생시킵니다.
        """
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError('token_expired')
        except jwt.InvalidTokenError:
            raise ValueError('invalid_token')
