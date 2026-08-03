# BizboxA MCP Server — 연결 가이드

## 구조 개요

```
MCP 호스트 (Claude / Cursor)
        │
        │  GET /sse   (Authorization: Bearer <token>)
        ▼
 BizboxA MCP Server  ←── SSE 스트림 유지
        │
        │  POST /messages?session_id=<uuid>
        ▼
   Tool 실행 (KIS / 환율 / 유가)
```

---

## 1단계: 서버 실행

```bash
cd mcp_server
python server.py
```

출력:
```
🚀 BizboxA MCP Server (HTTP SSE) 시작
   주소:         http://0.0.0.0:8000
   SSE 연결:     GET  http://0.0.0.0:8000/sse
   메시지 전송:  POST http://0.0.0.0:8000/messages
   토큰 발급:    POST http://0.0.0.0:8000/oauth/token
```

---

## 2단계: Access Token 발급

```bash
curl -X POST http://localhost:8000/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=claude-bizbox" \
  -d "client_secret=123"
```

응답:
```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "stock:read index:read exchange:read oil:read"
}
```

---

## 3단계: MCP 호스트 설정

### Claude Desktop

설정 파일 위치:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "bizbox": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer <2단계에서_발급받은_토큰>"
      }
    }
  }
}
```

### Cursor

설정 → MCP → Add Server:

```json
{
  "bizbox": {
    "url": "http://localhost:8000/sse",
    "headers": {
      "Authorization": "Bearer <토큰>"
    }
  }
}
```

---

## 제공 Tool 목록

| Tool 이름 | 설명 | 필수 파라미터 |
|-----------|------|---------------|
| `get_stock_price` | 국내 주식 실시간 시세 | `stock_code` (6자리) |
| `get_kospi_index` | KOSPI 지수 | 없음 |
| `get_kosdaq_index` | KOSDAQ 지수 | 없음 |
| `get_exchange_price` | 환율 (AP01/AP02/AP03) | 없음 (기본 AP01) |
| `get_oil_price` | 지역별 유가 | `area_code` (4자리) |

---

## 인증 흐름 요약

```
클라이언트                          서버
    │                                │
    │  POST /oauth/token             │
    │  (client_id, client_secret)    │
    │ ──────────────────────────────►│
    │                                │  DB에서 client 검증
    │  { access_token: "eyJ..." }    │  JWT 생성
    │ ◄──────────────────────────────│
    │                                │
    │  GET /sse                      │
    │  Authorization: Bearer eyJ...  │
    │ ──────────────────────────────►│
    │                                │  JWT 검증
    │  SSE 스트림 수립               │  MCP 세션 시작
    │ ◄──────────────────────────────│
    │                                │
    │  (MCP Tool 호출)               │
    │  POST /messages?session_id=... │
    │ ──────────────────────────────►│
    │                                │  Tool 실행
    │  SSE 이벤트로 결과 수신        │
    │ ◄──────────────────────────────│
```

---

## 주의사항

> [!WARNING]
> `access_token`은 1시간 후 만료됩니다. 만료 시 다시 `/oauth/token`으로 토큰을 재발급하고 MCP 호스트 설정을 업데이트하세요.

> [!NOTE]
> Cursor는 SSE 방식 MCP 지원이 Claude Desktop보다 제한적일 수 있습니다. 연결 오류 시 Cursor 버전을 확인하세요.
