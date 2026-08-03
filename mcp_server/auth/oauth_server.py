from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional
from auth.client_store import ClientStore
from auth.token_manager import TokenManager
import os

router = APIRouter()

MCP_SERVER_BASE: str = os.getenv('MCP_SERVER_BASE', 'http://192.168.2.66:8000')


@router.get('/.well-known/oauth-authorization-server')
def oauth_metadata():
    """
    MCP Client 가 자동으로 읽는 OAuth 서버 메타데이터입니다.
    Client Credentials 방식만 지원합니다.
    """
    return JSONResponse({
        'issuer': MCP_SERVER_BASE,
        'token_endpoint': f'{MCP_SERVER_BASE}/oauth/token',
        'grant_types_supported': ['client_credentials'],
        'token_endpoint_auth_methods_supported': ['client_secret_post'],
        'scopes_supported': [
            'stock:read',
            'index:read',
            'exchange:read',
            'oil:read'
        ]
    })


@router.post('/oauth/token')
async def issue_token(request: Request):
    """
    Client Credentials Grant 방식으로 Access Token 을 발급합니다.

    요청 파라미터 (application/x-www-form-urlencoded 또는 JSON):
        grant_type    : 'client_credentials' 고정
        client_id     : 등록된 클라이언트 ID
        client_secret : 등록된 클라이언트 시크릿
        scope         : 요청 권한 (선택, 없으면 클라이언트 기본 권한 사용)
    """
    # Content-Type 에 따라 파라미터 파싱
    content_type = request.headers.get('content-type', '')
    if 'application/json' in content_type:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)

    grant_type: Optional[str] = body.get('grant_type')
    client_id: Optional[str] = body.get('client_id')
    client_secret: Optional[str] = body.get('client_secret')
    scope: str = body.get('scope', '')

    # grant_type 확인
    if grant_type != 'client_credentials':
        raise HTTPException(
            status_code=400,
            detail={'error': 'unsupported_grant_type',
                    'error_description': 'grant_type must be client_credentials'}
        )

    # 필수 파라미터 확인
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail={'error': 'invalid_request',
                    'error_description': 'client_id and client_secret are required'}
        )

    # client_id / client_secret 검증
    client = ClientStore.verify(client_id, client_secret)
    if not client:
        raise HTTPException(
            status_code=401,
            detail={'error': 'invalid_client',
                    'error_description': 'client_id or client_secret is invalid'}
        )

    # scope 처리: 요청한 scope 이 없으면 클라이언트 기본 scopes 사용
    granted_scopes: list = scope.split() if scope else client.get('scopes', [])

    # Access Token 발급
    access_token = TokenManager.create_token(
        client_id=client_id,
        scopes=granted_scopes
    )

    return JSONResponse({
        'access_token': access_token,
        'token_type': 'Bearer',
        'expires_in': 3600,
        'scope': ' '.join(granted_scopes)
        # Client Credentials 는 refresh_token 없음
    })
