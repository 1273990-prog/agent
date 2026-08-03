from fastapi import Request, HTTPException
from auth.token_manager import TokenManager


async def verify_token(request: Request):
    """
    모든 MCP 요청에 적용되는 Bearer Token 검증 미들웨어입니다.
    검증 성공 시 request.state 에 client_id, scopes 를 저장합니다.
    """
    auth_header: str = request.headers.get('Authorization', '')

    if not auth_header.startswith('Bearer '):
        raise HTTPException(
            status_code=401,
            detail={'error': 'unauthorized',
                    'error_description': 'Bearer token is required'}
        )

    token = auth_header.replace('Bearer ', '', 1).strip()

    try:
        payload = TokenManager.verify_token(token)
        request.state.client_id = payload.get('sub')
        request.state.scopes = payload.get('scopes', [])
    except ValueError as e:
        error = str(e)
        if error == 'token_expired':
            raise HTTPException(
                status_code=401,
                detail={'error': 'token_expired',
                        'error_description': 'Access token has expired'}
            )
        raise HTTPException(
            status_code=401,
            detail={'error': 'invalid_token',
                    'error_description': 'Access token is invalid'}
        )
