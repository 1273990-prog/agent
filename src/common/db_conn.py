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
                            """,

        # ─── MCP 클라이언트 관리 쿼리 ───

        "SELECT_CLIENT_BY_ID": """
                            SELECT client_id, client_secret_hash, name, scopes, created_at
                            FROM mcp_clients
                            WHERE client_id = %(client_id)s
                            """,

        "SELECT_ALL_CLIENTS": """
                            SELECT client_id, name, scopes, created_at
                            FROM mcp_clients
                            ORDER BY created_at DESC
                            """,

        "INSERT_CLIENT": """
                            INSERT INTO mcp_clients
                                (client_id, client_secret_hash, name, scopes, created_at)
                            VALUES
                                (%(client_id)s, %(client_secret_hash)s,
                                 %(name)s, %(scopes)s, NOW())
                            """,

        "DELETE_CLIENT_BY_ID": """
                            DELETE FROM mcp_clients
                            WHERE client_id = %(client_id)s
                            """,

        # ─── 기업 코드 정보 저장 쿼리 ───

        "INSERT_CORP_CODE_INFO": """
                            INSERT INTO corp_code_info 
                                (rule_no, corp_code, corp_name, corp_eng_name, stock_code, modify_date, create_date)
                            VALUES 
                                (%(rule_no)s, %(corp_code)s, %(corp_name)s, %(corp_eng_name)s, %(stock_code)s, %(modify_date)s, NOW())
                            """,

        "SELECT_CORP_CODE_BY_NAME": """
                            SELECT rule_no, corp_code, corp_name
                            FROM corp_code_info
                            WHERE corp_name = %(corp_name)s
                            LIMIT 1
                            """,

        "SELECT_CORP_CODE_BY_STOCK_CODE": """
                            SELECT rule_no, corp_code, corp_name, stock_code
                            FROM corp_code_info
                            WHERE stock_code = %(stock_code)s
                            LIMIT 1
                            """,

        "SELECT_UNCOLLECTED_CORP_CODES": """
                            SELECT c.rule_no, c.corp_code, c.corp_name, c.stock_code
                            FROM corp_code_info c
                            WHERE NOT EXISTS (
                                SELECT 1
                                FROM fin_stmt_info f
                                WHERE f.corp_no = c.rule_no
                            )
                            ORDER BY c.rule_no
                            """,

        # ─── 재무제표 정보 저장 쿼리 ───

        "INSERT_FIN_STMT_INFO": """
                            INSERT INTO fin_stmt_info
                                (rule_no, corp_no, bsns_year, account_id, account_nm, account_detail, thstrm_amount, ord, thstrm_nm, fs_div, fs_nm, sj_div, sj_nm, rcept_no, reprt_code, create_date)
                            VALUES
                                (%(rule_no)s, %(corp_no)s, %(bsns_year)s, %(account_id)s, %(account_nm)s, %(account_detail)s, %(thstrm_amount)s::NUMERIC, %(ord)s::INTEGER, %(thstrm_nm)s, %(fs_div)s, %(fs_nm)s, %(sj_div)s, %(sj_nm)s, %(rcept_no)s, %(reprt_code)s, NOW())
                            """,

        "DELETE_FIN_STMT_INFO_BY_CORP_NO": """
                            DELETE FROM fin_stmt_info
                            WHERE corp_no = %(corp_no)s
                            """,

        # ─── 재무제표 벡터 임베딩 쿼리 ───

        "SELECT_FIN_STMT_FOR_VECTORIZE": """
                            SELECT f.rule_no, f.corp_no, f.bsns_year, f.account_id,
                                   f.account_nm, f.account_detail, f.thstrm_amount,
                                   f.sj_div, f.sj_nm, f.fs_div, f.fs_nm,
                                   f.rcept_no, f.reprt_code,
                                   c.corp_name
                            FROM fin_stmt_info f
                            JOIN corp_code_info c ON f.corp_no = c.rule_no
                            WHERE NOT EXISTS (
                                SELECT 1
                                FROM fin_stmt_embedding e
                                WHERE e.rel_no = f.rule_no
                            )
                            ORDER BY f.bsns_year DESC, c.corp_name
                            LIMIT 1000
                            """,

        "INSERT_FIN_STMT_EMBEDDING": """
                            INSERT INTO fin_stmt_embedding
                                (rule_no, rel_no, corp_name, bsns_year,
                                 sj_div, account_nm, document_text, embedding)
                            VALUES
                                (%(rule_no)s, %(rel_no)s, %(corp_name)s, %(bsns_year)s,
                                 %(sj_div)s, %(account_nm)s, %(document_text)s,
                                 %(embedding)s::vector)
                            """,

        "SEARCH_FIN_STMT_EMBEDDING": """
                            SELECT rule_no, rel_no, corp_name, bsns_year, account_nm,
                                   document_text,
                                   1 - (embedding <=> %(query_embedding)s::vector) AS similarity
                            FROM fin_stmt_embedding
                            WHERE (%(corp_name)s IS NULL OR corp_name = %(corp_name)s)
                              AND (%(bsns_year)s IS NULL OR bsns_year = %(bsns_year)s)
                            ORDER BY embedding <=> %(query_embedding)s::vector
                            LIMIT %(top_k)s
                            """,

        # ─── 수출입동향 정보 저장 쿼리 ───

        "INSERT_TRADE_TREND_INFO": """
                            INSERT INTO trade_trend_info
                                (rule_no, doc_title, publisher, report_date, period, create_date)
                            VALUES
                                (%(rule_no)s, %(doc_title)s, %(publisher)s, %(report_date)s::TIMESTAMPTZ, %(period)s::DATE, NOW())
                            """,

        "SELECT_TRADE_TREND_INFO_BY_TITLE_AND_PERIOD": """
                            SELECT rule_no, doc_title, publisher, report_date, period, create_date
                            FROM trade_trend_info
                            WHERE doc_title = %(doc_title)s AND period = %(period)s::DATE
                            LIMIT 1
                            """,

        "SELECT_ALL_TRADE_TREND_INFO": """
                            SELECT rule_no, doc_title, publisher, report_date, period, create_date
                            FROM trade_trend_info
                            ORDER BY period DESC, create_date DESC
                            """,

        "DELETE_TRADE_TREND_DETAIL_BY_INFO_NO": """
                            DELETE FROM trade_trend_detail
                            WHERE trade_trend_no = %(trade_trend_no)s
                            """,

        "DELETE_TRADE_TREND_INFO_BY_ID": """
                            DELETE FROM trade_trend_info
                            WHERE rule_no = %(rule_no)s
                            """,

        "INSERT_TRADE_TREND_DETAIL": """
                            INSERT INTO trade_trend_detail
                                (rule_no, trade_trend_no, trade_trend_text, trade_trend_section, contest_type, page, extra_meta, create_date)
                            VALUES
                                (%(rule_no)s, %(trade_trend_no)s, %(trade_trend_text)s, %(trade_trend_section)s, %(contest_type)s, %(page)s::INTEGER, %(extra_meta)s::JSONB, NOW())
                            """,

        "SELECT_TRADE_TREND_DETAIL_FOR_VECTORIZE": """
                            SELECT d.rule_no, d.trade_trend_no, d.trade_trend_text, d.trade_trend_section,
                                   d.contest_type, d.page, d.extra_meta,
                                   i.doc_title, i.publisher, i.period
                            FROM trade_trend_detail d
                            JOIN trade_trend_info i ON d.trade_trend_no = i.rule_no
                            WHERE d.embedding IS NULL
                            ORDER BY d.trade_trend_no, d.page, d.rule_no
                            """,

        "UPDATE_TRADE_TREND_DETAIL_EMBEDDING": """
                            UPDATE trade_trend_detail
                            SET embedding = %(embedding)s::vector
                            WHERE rule_no = %(rule_no)s
                            """,

        "SEARCH_TRADE_TREND_DETAIL_EMBEDDING": """
                            SELECT d.rule_no, d.trade_trend_no, d.trade_trend_text, d.trade_trend_section,
                                   d.contest_type, d.page, d.extra_meta,
                                   i.doc_title, i.publisher, i.period,
                                   1 - (d.embedding <=> %(query_embedding)s::vector) AS similarity
                            FROM trade_trend_detail d
                            JOIN trade_trend_info i ON d.trade_trend_no = i.rule_no
                            WHERE d.embedding IS NOT NULL
                              AND (%(period)s IS NULL OR i.period = %(period)s::DATE)
                              AND (%(item)s IS NULL OR d.extra_meta->>'item' = %(item)s)
                              AND (%(region)s IS NULL OR d.extra_meta->>'region' = %(region)s)
                              AND (%(contest_type)s IS NULL OR d.contest_type = %(contest_type)s)
                            ORDER BY d.embedding <=> %(query_embedding)s::vector
                            LIMIT %(top_k)s
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

            # 2) 쿼리 실행 (리스트 파라미터 전달 시 executemany 일괄 처리)
            if isinstance(bind_params, list):
                self.__cursor.executemany(self.__sql_query, bind_params)
            else:
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