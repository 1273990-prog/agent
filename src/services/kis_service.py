import json
from typing import Dict, Any
from services.base_service import BaseService
from services.registry import register_service
from common.constants import AgentConstants
from common.utils import AgentUtils

@register_service(AgentConstants.KIS)  # Registers the KIS service name dynamically
class KisService(BaseService):
    def __init__(self):
        super().__init__()
        self.__url_base: str = "https://openapi.koreainvestment.com:9443"

    def check_valid_token(self, config_json: str) -> str:
        try:
            config: Dict[str, Any] = config_json

            if not config:
                print("[오류] 설정을 불러올 수 없어 프로그램을 종료합니다.")
                return

            access_token = None

            db_host = config.get("db_host", "")
            port = config.get("port", "")
            database = config.get("database", "")
            username = config.get("username", "")
            password = config.get("password", "")
            appkey = config.get("appkey", "")
            appsecret = config.get("appsecret", "")

            get_data = {
                "net_value": {
                    "action": AgentConstants.SELECT,
                    "host": db_host,
                    "port": port,
                    "database": database,
                    "username": username,
                    "password": password
                },
                "data_value": {
                    "query_key": "SELECT_TOKEN_BY_DATE",
                    "params": {'svc_type': 'HIS'}
                }
            }

            get_data_json = json.dumps(get_data)

            token_data = self.get_valid_token_to_json(get_data_json)

            if token_data:
                access_token = token_data.get("access_token")
                print("[정보] 데이터베이스에서 기존 유효 토큰을 로드했습니다.")
                return access_token
            else:
                print("[정보] 유효한 토큰이 없거나 만료되었습니다. 새 토큰을 요청합니다...")
                token_request_json = json.dumps({
                "appkey": appkey,
                "appsecret": appsecret
                })

                try:
                    token_data = self.get_access_token_to_json(token_request_json)

                    access_token = token_data.get("access_token")

                    token_data["rule_no"] = AgentUtils.get_rule_no()
                    token_data["svc_type"] = "HIS"

                    set_data = {
                        "net_value": {
                            "action": AgentConstants.INSERT,
                            "host": db_host,
                            "port": port,
                            "database": database,
                            "username": username,
                            "password": password
                        },
                        "data_value": {
                            "query_key": "INSERT_TOKEN_INFO",
                            "params": token_data
                        }
                    }

                    self.set_valid_token_to_string(json.dumps(set_data))
                    print("[정보] 새 토큰을 데이터베이스에 성공적으로 저장했습니다.")

                    return access_token
                
                except Exception as e:
                    print(f"[오류] 토큰 발급 및 저장 중 문제가 발생했습니다: {e}")
                    return None

        except Exception as e:
            print(e)
            raise e
    
    def set_valid_token_to_json(self, model_json: str) -> Dict[str, Any]:
        try:
            return self._execute_and_convert(self.__set_valid_token, model_json, to_json=True)
        except Exception as e:
            print(e)
            raise e

    def set_valid_token_to_string(self, model_json: str) -> str:
        try:
            return self._execute_and_convert(self.__set_valid_token, model_json, to_json=False)
        except Exception as e:
            print(e)
            raise e

    def get_valid_token_to_json(self, model_json: str) -> Dict[str, Any]:
        try:
            return self._execute_and_convert(self.__get_valid_token, model_json, to_json=True)
        except Exception as e:
            print(e)
            raise e

    def get_valid_token_to_string(self, model_json: str) -> str:
        try:
            return self._execute_and_convert(self.__get_valid_token, model_json, to_json=False)
        except Exception as e:
            print(e)
            raise e


    def get_access_token_to_json(self, model_json: str) -> Dict[str, Any]:
        try:
            return self._execute_and_convert(self.__get_access_token, model_json, to_json=True)
        except Exception as e:
            print(e)
            raise e

    def get_access_token_to_string(self, model_json: str) -> str:
        try:
            return self._execute_and_convert(self.__get_access_token, model_json, to_json=False)
        except Exception as e:
            print(e)
            raise e

    def get_kospi_index_to_json(self, model_json: str) -> Dict[str, Any]:
        try:
            return self._execute_and_convert(self.__get_kospi_index, model_json, to_json=True)
        except Exception as e:
            print(e)
            raise e

    def get_kospi_index_to_string(self, model_json: str) -> str:
        try:
            return self._execute_and_convert(self.__get_kospi_index, model_json, to_json=False)
        except Exception as e:
            print(e)
            raise e

    def get_stock_price_to_json(self, model_json: str) -> Dict[str, Any]:
        try:
            return self._execute_and_convert(self.__get_stock_price, model_json, to_json=True)
        except Exception as e:
            print(e)
            raise e

    def get_stock_price_to_string(self, model_json: str) -> str:
        try:
            return self._execute_and_convert(self.__get_stock_price, model_json, to_json=False)
        except Exception as e:
            print(e)
            raise e

    def __get_access_token(self, model_json: str) -> str:
        try:
            # 외부에서 들어온 데이터 JSON을 파이썬 딕셔너리로 즉시 파싱
            model_data: Dict[str, Any] = json.loads(model_json)

            if not isinstance(model_data, dict):
                raise

            net_value: Dict[str, Any] = {}

            path = "/oauth2/tokenP"
            net_value["url"] = f"{self.__url_base}{path}"

            # HTTP 기본 통신 정보 조립
            net_value["method"] = AgentConstants.POST
            net_value["contentType"] = AgentConstants.JSON
            
            # 입력 데이터 내부에 service_map 구조가 없다면 빈 딕셔너리로 초기화
            if "service_map" not in model_data:
                model_data["service_map"] = {}
                
            # 고유 요구 필수 파라미터 강제 주입
            model_data["service_map"]["grant_type"] = "client_credentials"
            model_data["service_map"]["appkey"] = model_data.get("appkey", "")
            model_data["service_map"]["appsecret"] = model_data.get("appsecret", "")

            # 부모 클래스(BaseService)의 규격에 맞게 다시 JSON 문자열로 직렬화하여 바인딩
            data_value_json = json.dumps(model_data["service_map"])

            # 부모의 동기식 HTTP 요청 처리 메서드 작동
            net_value_json = json.dumps(net_value)
            response_string = self._run(net_value_json, data_value_json)

            return response_string if response_string is not None else ""

        except Exception as e:
            raise e

    def __get_kospi_index(self, model_json: str) -> str:
        try:
            # 외부에서 들어온 데이터 JSON을 파이썬 딕셔너리로 즉시 파싱
            model_data: Dict[str, Any] = json.loads(model_json)

            if not isinstance(model_data, dict):
                raise

            net_value: Dict[str, Any] = {}

            path = "/uapi/domestic-stock/v1/quotations/inquire-index-price"
            net_value["url"] = f"{self.__url_base}{path}"

            # HTTP 기본 통신 정보 조립
            net_value["method"] = AgentConstants.GET
            net_value["contentType"] = AgentConstants.JSON
            net_value["authType"] = AgentConstants.BEARER
            net_value["accessToken"] = model_data.get("access_token", "")
            
            # KIS API 헤더 주입 (decoupled 설계에 맞추어 headers 사전에 담아 HttpConn으로 전달)
            net_value["headers"] = {
                "appkey": model_data.get("appkey", ""),
                "appsecret": model_data.get("appsecret", ""),
                "tr_id": model_data.get("tr_id", ""),
                "custtype": model_data.get("custtype", "")
            }
            
            # 입력 데이터 내부에 service_map 구조가 없다면 빈 딕셔너리로 초기화
            if "service_map" not in model_data:
                model_data["service_map"] = {}
                
            # 고유 요구 필수 파라미터 강제 주입     
            model_data["service_map"]["fid_cond_mrkt_div_code"] = model_data.get("fid_cond_mrkt_div_code", "")
            model_data["service_map"]["fid_input_iscd"] = model_data.get("fid_input_iscd", "")

            # 5. 부모 클래스(BaseAgent)의 규격에 맞게 다시 JSON 문자열로 직렬화하여 바인딩
            data_value_json = json.dumps(model_data["service_map"])

            # 부모의 동기식 HTTP 요청 처리 메서드 작동
            net_value_json = json.dumps(net_value)
            response_string = self._run(net_value_json, data_value_json)

            return response_string if response_string is not None else ""

        except Exception as e:
            raise e

    def __get_stock_price(self, model_json: str) -> str:
        try:
            # 외부에서 들어온 데이터 JSON을 파이썬 딕셔너리로 즉시 파싱
            model_data: Dict[str, Any] = json.loads(model_json)

            if not isinstance(model_data, dict):
                raise

            net_value: Dict[str, Any] = {}

            path = "/uapi/domestic-stock/v1/quotations/inquire-price"
            net_value["url"] = f"{self.__url_base}{path}"

            # HTTP 기본 통신 정보 조립
            net_value["method"] = AgentConstants.GET
            net_value["contentType"] = AgentConstants.JSON
            net_value["authType"] = AgentConstants.BEARER
            net_value["accessToken"] = model_data.get("access_token", "")
            
            # KIS API 헤더 주입 (decoupled 설계에 맞추어 headers 사전에 담아 HttpConn으로 전달)
            net_value["headers"] = {
                "appkey": model_data.get("appkey", ""),
                "appsecret": model_data.get("appsecret", ""),
                "tr_id": model_data.get("tr_id", "")
            }
            
            # 입력 데이터 내부에 service_map 구조가 없다면 빈 딕셔너리로 초기화
            if "service_map" not in model_data:
                model_data["service_map"] = {}
                
            # 고유 요구 필수 파라미터 강제 주입
            model_data["service_map"]["fid_cond_mrkt_div_code"] = model_data.get("fid_cond_mrkt_div_code", "")
            model_data["service_map"]["fid_input_iscd"] = model_data.get("fid_input_iscd", "")

            # 5. 부모 클래스(BaseAgent)의 규격에 맞게 다시 JSON 문자열로 직렬화하여 바인딩
            data_value_json = json.dumps(model_data["service_map"])

            # 부모의 동기식 HTTP 요청 처리 메서드 작동
            net_value_json = json.dumps(net_value)
            response_string = self._run(net_value_json, data_value_json)

            return response_string if response_string is not None else ""
        
        except Exception as e:
            raise e
        
    def __get_valid_token(self, model_json: str) -> str:
        try:
            model_data: Dict[str, Any] = json.loads(model_json)

            if not isinstance(model_data, dict):
                raise

            net_value = model_data.get("net_value", {}) if model_data else {}
            data_value = model_data.get("data_value", {}) if model_data else {}

            net_value_json = json.dumps(net_value)
            data_value_json = json.dumps(data_value)

            response_string_list = self._run_sql(net_value_json, data_value_json)
            
            response_list = json.loads(response_string_list)

            response_string = json.dumps(response_list[0])

            return response_string if response_string is not None else ""
        
        except Exception as e:
            raise e
        
    def __set_valid_token(self, model_json: str) -> str:
        try:
            model_data: Dict[str, Any] = json.loads(model_json)

            if not isinstance(model_data, dict):
                raise

            net_value = model_data.get("net_value", {}) if model_data else {}
            data_value = model_data.get("data_value", {}) if model_data else {}

            net_value_json = json.dumps(net_value)
            data_value_json = json.dumps(data_value)

            response_string = self._run_sql(net_value_json, data_value_json)
            
            return response_string if response_string is not None else ""
        
        except Exception as e:
            raise e