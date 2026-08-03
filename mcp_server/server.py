import sys
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent

# auth / tools 모듈 경로 추가
sys.path.insert(0, os.path.dirname(__file__))

from auth.oauth_server import router as oauth_router
from auth.token_manager import TokenManager
from tools.stock_tools import get_stock_price, get_kospi_index, get_kosdaq_index
from tools.exchange_tools import get_exchange_price
from tools.oil_tools import get_oil_price


# ─────────────────────────────────────────────
# MCP Server 인스턴스
# ─────────────────────────────────────────────

mcp = Server('sdb-mcp')


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """MCP 호스트(Claude, Cursor, Hermes 등)가 연결 시 자동으로 조회하는 Tool 목록."""
    return [
        Tool(
            name='get_stock_price',
            description=(
                '국내 주식 실시간 시세를 조회합니다.\n'
                '6자리 숫자 종목코드를 입력하세요. 예: 삼성전자 005930'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'stock_code': {
                        'type': 'string',
                        'description': '6자리 숫자 종목코드 (예: 005930)',
                    }
                },
                'required': ['stock_code'],
            },
        ),
        Tool(
            name='get_kospi_index',
            description='KOSPI 지수를 실시간으로 조회합니다. 입력 파라미터 없음.',
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
        Tool(
            name='get_kosdaq_index',
            description='KOSDAQ 지수를 실시간으로 조회합니다. 입력 파라미터 없음.',
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
        Tool(
            name='get_exchange_price',
            description=(
                '환율 정보를 조회합니다.\n'
                'data_code 선택:\n'
                '  AP01 - 환율 (기본값)\n'
                '  AP02 - 대고객환율\n'
                '  AP03 - 재정환율'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'data_code': {
                        'type': 'string',
                        'enum': ['AP01', 'AP02', 'AP03'],
                        'description': '조회 유형 코드 (기본값: AP01)',
                        'default': 'AP01',
                    }
                },
                'required': [],
            },
        ),
        Tool(
            name='get_oil_price',
            description=(
                '지역별 유가 정보를 조회합니다.\n'
                'prod_code 선택:\n'
                '  B034 - 고급휘발유\n'
                '  B027 - 보통휘발유 (기본값)\n'
                '  C004 - 경유\n'
                '  D047 - 등유\n'
                '  K105 - LPG(부탄)\n'
                'area_code: 4자리 숫자 지역 구분코드 (예: 서울금천 0125)'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'prod_code': {
                        'type': 'string',
                        'enum': ['B034', 'B027', 'C004', 'D047', 'K105'],
                        'description': '제품코드 (기본값: B027 보통휘발유)',
                        'default': 'B027',
                    },
                    'area_code': {
                        'type': 'string',
                        'description': '4자리 숫자 지역 구분코드 (예: 0125)',
                    },
                },
                'required': ['area_code'],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """MCP 호스트가 Tool 실행을 요청할 때 호출됩니다."""
    try:
        if name == 'get_stock_price':
            result = get_stock_price(arguments.get('stock_code', ''))

        elif name == 'get_kospi_index':
            result = get_kospi_index()

        elif name == 'get_kosdaq_index':
            result = get_kosdaq_index()

        elif name == 'get_exchange_price':
            result = get_exchange_price(arguments.get('data_code', 'AP01'))

        elif name == 'get_oil_price':
            result = get_oil_price(
                arguments.get('prod_code', 'B027'),
                arguments.get('area_code', ''),
            )

        else:
            raise ValueError(f'알 수 없는 Tool 이름: {name}')

        return [TextContent(type='text', text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type='text', text=f'[오류] {e}')]


# ─────────────────────────────────────────────
# Streamable HTTP Transport 초기화 (MCP 2025 표준)
# ─────────────────────────────────────────────

# NOTE: StreamableHTTPSessionManager는 단일 /mcp 엔드포인트에서
#       POST(요청) 와 GET(SSE 스트림 업그레이드) 를 모두 처리합니다.
session_manager = StreamableHTTPSessionManager(
    app=mcp,
    json_response=False,   # SSE 스트림 응답 사용 (json_response=True 시 단순 JSON 응답)
    stateless=False,       # 세션 상태 유지 (stateless=True 시 매 요청마다 새 세션)
)


def _verify_bearer(request: Request) -> str | None:
    """
    Authorization 헤더에서 Bearer 토큰을 검증합니다.
    성공 시 client_id(str) 반환, 실패 시 None 반환.
    """
    auth_header: str = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header.replace('Bearer ', '', 1).strip()
    try:
        payload = TokenManager.verify_token(token)
        return payload.get('sub')
    except ValueError:
        return None


# ─────────────────────────────────────────────
# FastAPI 앱
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan 핸들러.
    StreamableHTTPSessionManager.run() 은 내부 anyio TaskGroup 을 초기화하므로
    앱 시작 시 반드시 실행되어야 합니다.
    """
    async with session_manager.run():
        yield


app = FastAPI(
    title='SDB MCP Server',
    description='KIS 주식/지수, 환율, 유가 조회 MCP 서버 (Streamable HTTP + OAuth2 Client Credentials)',
    version='0.1.0',
    lifespan=lifespan,
)

# OAuth2 라우터 등록 (토큰 발급 + /.well-known 메타데이터)
app.include_router(oauth_router)


# ─────────────────────────────────────────────
# MCP Streamable HTTP 단일 엔드포인트 (raw ASGI 미들웨어)
# ─────────────────────────────────────────────
# NOTE: app.mount('/mcp', ...) 는 Starlette 가 scope['path'] 에서 prefix 를
#       제거(스트립)하고 서브앱에 전달합니다.
#       session_manager 가 '/또는 빈 경로를 받아 404 를 반환하는 문제가 발생합니다.
#       미들웨어 방식은 scope 를 수정하지 않고 /mcp 경로를 가로챔서
#       원래 경로가 유지된 상태로 session_manager 에 위임합니다.


async def _handle_mcp_request(scope, receive, send):
    """
    /mcp 경로에 대한 인증 + session_manager 위임.
    - POST /mcp : 클라이언트 → 서버 메시지 전송 (Tool 호출 등)
    - GET  /mcp : 서버 → 클라이언트 SSE 스트림
    - DELETE /mcp : 세션 종료

    Hermes / Claude Desktop / Cursor 설정 예시:
        {
            "mcpServers": {
                "sdb": {
                    "url": "http://<host>:<port>/mcp",
                    "headers": { "Authorization": "Bearer <access_token>" }
                }
            }
        }
    """
    # Bearer 토큰 검증 (raw headers: list[tuple[bytes, bytes]])
    auth_header = ''
    for name, value in scope.get('headers', []):
        if name.lower() == b'authorization':
            auth_header = value.decode('latin-1')
            break

    if not auth_header.startswith('Bearer '):
        token_ok = False
    else:
        token = auth_header.replace('Bearer ', '', 1).strip()
        try:
            payload = TokenManager.verify_token(token)
            token_ok = bool(payload.get('sub'))
        except ValueError:
            token_ok = False

    if not token_ok:
        body = json.dumps({
            'error': 'unauthorized',
            'error_description': 'Valid Bearer token is required. '
                                 'Issue a token via POST /oauth/token',
        }).encode()
        await send({
            'type': 'http.response.start',
            'status': 401,
            'headers': [
                (b'content-type', b'application/json'),
                (b'content-length', str(len(body)).encode()),
            ],
        })
        await send({'type': 'http.response.body', 'body': body})
        return

    # scope 변경 없이 원래 경로 그대로 session_manager 에 위임
    await session_manager.handle_request(scope, receive, send)


class MCPMiddleware:
    """
    Raw ASGI 미들웨어.
    /mcp 또는 /mcp/ 로 시작하는 HTTP 요청을 FastAPI 라우터 이전에 가로채
    scope['path'] 를 수정하지 않은 체로 session_manager 에 위임합니다.
    """

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http':
            path: str = scope.get('path', '')
            if path == '/mcp' or path.startswith('/mcp/'):
                await _handle_mcp_request(scope, receive, send)
                return
        await self._app(scope, receive, send)


app.add_middleware(MCPMiddleware)


# ─────────────────────────────────────────────
# 서버 정보 엔드포인트
# ─────────────────────────────────────────────

@app.get('/')
def root():
    """서버 상태 및 MCP 연결 정보 확인"""
    return {
        'server': 'SDB MCP Server',
        'version': '0.1.0',
        'protocol': 'MCP Streamable HTTP (2025 표준)',
        'status': 'running',
        'mcp': {
            'endpoint': 'GET|POST|DELETE /mcp  (Authorization: Bearer <token> 필요)',
            'tools': [
                'get_stock_price    - 국내 주식 실시간 시세',
                'get_kospi_index    - KOSPI 지수',
                'get_kosdaq_index   - KOSDAQ 지수',
                'get_exchange_price - 환율',
                'get_oil_price      - 지역별 유가',
            ],
        },
        'auth': {
            'type':           'OAuth2 Client Credentials',
            'token_endpoint': '/oauth/token',
            'metadata':       '/.well-known/oauth-authorization-server',
        },
    }


# ─────────────────────────────────────────────
# 서버 실행
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import uvicorn

    host = os.getenv('MCP_SERVER_HOST', '192.168.2.66')
    port = int(os.getenv('MCP_SERVER_PORT', '8000'))

    print(f'\n BizboxA MCP Server (Streamable HTTP) 시작')
    print(f'   주소:       http://{host}:{port}')
    print(f'   MCP:        GET|POST|DELETE http://{host}:{port}/mcp')
    print(f'   토큰 발급:  POST http://{host}:{port}/oauth/token')
    print(f'   서버 정보:  GET  http://{host}:{port}/')
    print()

    uvicorn.run(app, host=host, port=port)