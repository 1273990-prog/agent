import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, Any
from common.constants import AgentConstants

SAFE_QUERY_REGISTRY: Dict[str, str] = {    
        "SELECT_TOKEN_BY_DATE": """
                            SELECT * 
                            FROM token_info 
                            WHERE svc_type = %(svc_type)s
                            AND access_token_token_expired > NOW()
                            """,                                
 
        "INSERT_TOKEN_INFO": """
                            INSERT INTO token_info 
                            (rule_no, svc_type, access_token, access_token_token_expired, token_type, expires_in, create_date) 
                            VALUES   
                            (%(rule_no)s, %(svc_type)s, %(access_token)s, %(access_token_token_expired)s::TIMESTAMPTZ , %(token_type)s, %(expires_in)s::INTEGER, NOW())
                            """                     
}

class DbConn:
    def __init__(self, net_value_json: str):
        self.__connection: Optional[psycopg2.extensions.connection] = None
        self.__cursor: Optional[psycopg2.extensions.cursor] = None
        
        self.__sql_query: str = ""
        self.__action: str = ""  # SELECT, INSERT, UPDATE, DELETE 등

        # 1. 받아온 데이터베이스 연결 설정 JSON 문자열을 딕셔너리로 변환
        try:
            self.__net_value: Dict[str, Any] = json.loads(net_value_json)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON format: {e}")
            raise e
            
        self.__data_value: Optional[Dict[str, Any]] = None

        # 초기 연결 설정 빌드
        self._create()

    # --- 외부 노출 프로퍼티들 ---
    @property
    def net_value(self) -> Dict[str, Any]:
        return self.__net_value

    @net_value.setter
    def net_value(self, net_value_json: str):
        self.__net_value = json.loads(net_value_json)

    @property
    def data_value(self) -> Optional[Dict[str, Any]]:
        return self.__data_value

    def create_request(self, data_value_json: str) -> str:
        try:
            self.__data_value = json.loads(data_value_json)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON format: {e}")
            raise e

        query_key = ""

        try:
            # JSON 데이터 내부에서 실행할 SQL 쿼리문 추출
            query_key = self.__data_value.get("query_key", "")

            # 서버 내부에서 매핑된 안전한 정적 쿼리문 할당
            self.__sql_query = SAFE_QUERY_REGISTRY[query_key]

            return self.__sql_query
        except Exception as e:
            print(f"Security Alert: Unauthorized Query Key Requested: {query_key}")
            raise e                                

    def _create(self):
        """__net_value 딕셔너리에서 DB 접속 기본 필드 추출"""
        self.__action = self.__net_value.get("action", "")

    def _create_action_type(self):
        pass
        """요청받은 작업 종류를 식별 및 보정"""
        """
        # HttpConn의 DELPOST -> DELETE 변환 매칭 구간과 대응됩니다.
        if self.__action == AgentConstants.INSERT_PROC:
            self.__action = AgentConstants.INSERT
        elif self.__action == AgentConstants.UPDATE_PROC:
            self.__action = AgentConstants.UPDATE
        """

    def _bind_variables(self):
        """쿼리 매개변수 데이터 상태 콘솔 출력 및 검증"""
        if self.__data_value and "params" in self.__data_value:
            print(f"DB 파라미터 바인딩 완료\n{self.__data_value['params']}")

    # 3. 실제 DB 접속 및 쿼리 실행 후 결과를 JSON 텍스트 문자열로 반환 (HttpConn.create_response 대응)
    def create_response(self) -> str:
        """데이터베이스 연결 후 쿼리를 실행하고 결과를 JSON 스트링으로 리턴"""
        try:
            # net_value에 포함된 DB 접속 정보 추출 (호스트, 포트, DB명, 계정 등)
            db_args = {
                "host": self.__net_value.get("host", ""),
                "port": int(self.__net_value.get("port", 0)),
                "database": self.__net_value.get("database", ""),
                "user": self.__net_value.get("username", ""),
                "password": self.__net_value.get("password", "")
            }

            # 1) DB 커넥션 및 커서 오픈
            self.__connection = psycopg2.connect(**db_args)

            self.__connection.set_client_encoding('UTF-8') 

            # RealDictCursor를 사용하여 SELECT 결과를 딕셔너리 리스트 구조로 파싱 유도
            self.__cursor = self.__connection.cursor(cursor_factory=RealDictCursor)

            # Query에 바인딩할 파라미터 추출
            bind_params = self.__data_value.get("params", {}) if self.__data_value else {}

            # 2) 쿼리 실행
            self.__cursor.execute(self.__sql_query, bind_params)

            # 3) 액션에 따른 반환 데이터 처리 (HttpConn의 ReadToEnd Stream 처리와 대응)
            result_data: Any = None

            if self.__action == AgentConstants.SELECT:
                rows = self.__cursor.fetchall()
                # SELECT 계열이면 결과 로우 전체 Fetch
                result_data = [{}] if len(rows) == 0 else rows
            else:
                # INSERT, UPDATE, DELETE 계열이면 트랜잭션 반영 및 영향받은 행 수 리턴
                self.__connection.commit()
                result_data = {"affected_rows": self.__cursor.rowcount, "status": "success"}

            # 결과를 JSON String으로 직렬화하여 반환
            return json.dumps(result_data, ensure_ascii=False, default=str)

        except psycopg2.Error as e:
            print("Database Response Exception")
            if self.__connection is not None:
                print(f"SQLState: {e.pgcode}")
                print(f"ErrorMessage: {e.pgerror}")
            # 트랜잭션 롤백 처리
            if self.__connection:
                self.__connection.rollback()
            raise e
        except Exception as e:
            print(f"Failed to create response: {e}")
            raise e
        finally:
            # 4) 자원 해제 부 (HttpConn의 session.close() 스트림 해제 관리와 대응)
            if self.__cursor:
                self.__cursor.close()
            if self.__connection:
                self.__connection.close()