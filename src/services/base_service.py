from typing import Optional
from common.http_conn import HttpConn
from common.db_conn import DbConn
from common.constants import AgentConstants
import json

class BaseService:
    def __init__(self):
        pass

    def _run(self, net_value_json: str, data_value_json: str) -> Optional[str]:
        try:
            http_conn: Optional[HttpConn] = None

            http_conn = HttpConn(net_value_json)
            http_conn.create_request(data_value_json)

            return http_conn.create_response()
        except Exception as e:
            print(e)
            raise e
        
    def _run_sql(self, net_value_json: str, data_value_json: str) -> Optional[str]:        
        try:
            db_conn: Optional[DbConn] = None

            net_value_json = json.loads(net_value_json)
            data_value_json = json.loads(data_value_json)

            # DbConn 인스턴스 생성                                                        
            db_conn = DbConn(json.dumps(net_value_json))                                
                                                                     
            # SAFE_QUERY_REGISTRY에 존재하는 키와 바인딩할 파라미터 구성 
            query_data = {                                             
                "query_key": data_value_json.get("query_key"),                     
                "params": data_value_json.get("params")                                                        
            }                                                            
            query_data_json = json.dumps(query_data)                      
                                                                     
            # 쿼리 바인딩 요청 실행                                      
            db_conn.create_request(query_data_json)

            return db_conn.create_response()                            
        except Exception as e:
            print(e)
            raise e
                                                                    