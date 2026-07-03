import requests
import json
import base64
from typing import Optional, Dict, Any
from common.constants import AgentConstants

class HttpConn:
    # net_value의 타입을 str(JSON 문자열)로 변경합니다.
    def __init__(self, net_value_json: str):
        self.__web_req: Optional[requests.Request] = None
        self.__web_resp: Optional[requests.Request] = None
        self.__post_data: str = ""
        self.__url: str = ""
        self.__method: str = ""

        # 받아온 JSON 문자열을 파이썬 딕셔너리로 변환(Parse)하여 저장합니다.
        try:
            self.__net_value: Dict[str, Any] = json.loads(net_value_json)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON format: {e}")
            raise e
            
        self.__data_value: Optional[Dict[str, Any]] = None

        self._create()

    # --- 외부 노출 프로퍼티들 ---
    @property
    def net_value(self) -> Dict[str, Any]:
        return self.__net_value

    # 데이터 입력 시에도 JSON 문자열을 받아 처리할 수 있도록 Setter 수정
    @net_value.setter
    def net_value(self, value_json: str):
        self.__net_value = json.loads(value_json)

    @property
    def data_value(self) -> Optional[Dict[str, Any]]:
        return self.__data_value

    # create_request에 들어오는 데이터 데이터도 JSON 문자열로 받도록 처리
    def create_request(self, data_value_json: str) -> requests.Request:
        try:
            self.__data_value = json.loads(data_value_json)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON format: {e}")
            raise e

        try:
            self.__web_req = requests.Request()
            self.__web_req.url = self.__url
            self.__web_req.headers = {}

            if self.__method == AgentConstants.DELPOST:
                self.__web_req.method = AgentConstants.DELETE
            elif self.__method == AgentConstants.PUTPOST:
                self.__web_req.method = AgentConstants.PUT
            else:
                self.__web_req.method = self.__method

            self._create_req_param()

            self._create_auth()
            self._create_header()
            self._create_accept()
            self._create_content_type()
            self._create_req_stream()

            return self.__web_req
        except Exception as e:
            print(f"Failed to create request: {e}")
            raise e

    # (이하 메서드 내부 logic은 상단 변환 과정에서 파싱된 self.__net_value 딕셔너리를 그대로 사용하므로 수정 불필요)
    def _create(self):
        self.__url = self.__net_value.get("url", "")
        self.__method = self.__net_value.get("method", "")

    def _create_req_param(self):
        match self.__method:
            case AgentConstants.DELETE | AgentConstants.PUT | AgentConstants.GET: self._add_uri()
            case AgentConstants.DELPOST | AgentConstants.PUTPOST | AgentConstants.POST | AgentConstants.PATCH: self._add_data()
            case _: self._add_uri()

    def _create_auth(self):
        auth_type = self.__net_value.get("authType")
        if not auth_type: return
        match auth_type:
            case AgentConstants.BASIC:
                username = self.__net_value.get("username", "")
                password = self.__net_value.get("password")
                auth_str = username if password is None else f"{username}:{password}"
                encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
                self.__web_req.headers["Authorization"] = f"Basic {encoded_auth}"
            case AgentConstants.BEARER:
                self.__web_req.headers["Authorization"] = f"Bearer {self.__net_value.get('accessToken', '')}"

    def _create_header(self):
        custom_headers = self.__net_value.get("headers", {})
        for key, val in custom_headers.items():
            self.__web_req.headers[key] = val

    def _create_accept(self):
        accept_type = self.__net_value.get("accept")
        if accept_type:
            self.__web_req.headers["Accept"] = accept_type

    def _create_content_type(self):
        self.__web_req.headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
        content_type = self.__net_value.get("contentType")
        if not content_type: return
        match content_type:
            case AgentConstants.JSON: self.__web_req.headers["Content-Type"] = "application/json"
            case AgentConstants.OCTET: self.__web_req.headers["Content-Type"] = "application/octet-stream"
            case AgentConstants.MULTIPART: self.__web_req.headers["Content-Type"] = f"multipart/form-data; boundary={self.boundary}"

    def _add_uri(self):
        try:
            if self.__data_value:
            # requests.Request 객체의 params에 딕셔너리를 주면 자동 인코딩됩니다.
                self.__web_req.params = self.__data_value
        except Exception as e:
            print(f"Failed to add uri: {e}")
            raise e

    def _add_data(self):
        try:
            if not self.__data_value:
                return

            content_type = self.__net_value.get("contentType")
            
            if content_type == AgentConstants.JSON:
                # JSON이면 json 파라미터에 딕셔너리 주입 (헤더까지 자동 세팅)
                self.__web_req.json = self.__data_value
            else:
                # 기본 폼 형태면 data 파라미터에 딕셔너리 주입 (x-www-form-urlencoded 자동 인코딩)
                self.__web_req.data = self.__data_value
        except Exception as e:
            print(f"Failed to add data: {e}")
            raise e

    def _create_req_stream(self):
        try:
            # C#의 복잡한 조건 검사를 리스트 포함 여부(in)로 간결하게 단축
            target_methods = [AgentConstants.POST, AgentConstants.DELPOST, AgentConstants.PUTPOST, AgentConstants.PATCH]
            if self.__method not in target_methods:
                return

            # 파이썬 requests 객체는 데이터 스트림을 직접 열어 보낼 필요 없이, 
            # 인코딩된 문자열이나 바이트 데이터를 .data 속성에 대입해주면 전송 시 자동 스트리밍 처리됩니다.
            # Content-Length도 전송 시 라이브러리가 알아서 계산하여 헤더에 주입합니다.
            if self.__web_req.headers.get("Content-Type") == "application/json":
                # 만약 Content-Type이 JSON 명세라면 딕셔너리를 그대로 인코딩하여 주입
                self.__web_req.data = json.dumps(self.__data_value)
            else:
                # 기본 폼 인코딩 형태라면 가공된 post_data 문자열을 바이트 변환 후 주입
                self.__web_req.data = self.__post_data.encode("utf-8")

        except Exception as e:
            print(f"Failed to create request stream: {e}")
            raise e

    def create_response(self) -> str:
        session = requests.Session()
        try:
            # 1. 지금까지 빌드된 Request 객체를 최종 준비(prepare) 상태로 만듭니다.
            prepared_request = session.prepare_request(self.__web_req)
            
            # 2. 서버로 동기 전송 후 응답 수신
            self.__web_resp = session.send(prepared_request)
            
            # 3. HTTP 에러 상태(4xx, 5xx)일 경우 자동으로 예외(HTTPError)를 발생시켜 
            #    C#의 WebException 캐치 블록 흐름으로 유도합니다.
            self.__web_resp.raise_for_status()

            # 4. StreamReader.ReadToEnd()와 동일하게 전체 본문 텍스트 반환
            return self.__web_resp.text

        except requests.exceptions.HTTPError as e:
            print("Response Exception")
            if self.__web_resp is not None:
                # 상태 코드 출력
                print(self.__web_resp.status_code)
                # 에러 바디 텍스트 출력 (StreamReader 대응)
                print(self.__web_resp.text)
            raise e
        except Exception as e:
            print(f"Failed to create response: {e}")
            raise e
        finally:
            # 파이썬의 requests 세션은 connection pool을 사용하므로 
            # C#처럼 스트림을 일일이 close()하지 않아도 자동으로 안전하게 소멸 자원 관리가 됩니다.
            session.close()