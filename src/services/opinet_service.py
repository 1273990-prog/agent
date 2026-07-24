import json
from typing import Dict, Any
from services.base_service import BaseService
from services.registry import register_service
from common.constants import AgentConstants

@register_service(AgentConstants.OPINET)  # Registers the OPINET service name dynamically
class OpinetService(BaseService):
    def __init__(self):
        super().__init__()
        self.__url_base: str = "https://www.opinet.co.kr"

    def get_oil_price_to_json(self, model_json: str) -> Dict[str, Any]:
        try:
            return self._execute_and_convert(self.__get_oil_price, model_json, to_json=True)
        except Exception as e:
            print(e)
            raise e

    def get_oil_price_to_string(self, model_json: str) -> str:
        try:
            return self._execute_and_convert(self.__get_oil_price, model_json, to_json=False)
        except Exception as e:
            print(e)
            raise e

    def __get_oil_price(self, model_json: str) -> str:
        try:
            # 외부에서 들어온 데이터 JSON을 파이썬 딕셔너리로 즉시 파싱
            model_data: Dict[str, Any] = json.loads(model_json)

            if not isinstance(model_data, dict):
                raise

            net_value: Dict[str, Any] = {}

            path = "/api/lowTop10.do"
            net_value["url"] = f"{self.__url_base}{path}"

            # HTTP 기본 통신 정보 조립
            net_value["method"] = AgentConstants.GET
            net_value["contentType"] = AgentConstants.JSON
            
            # 입력 데이터 내부에 service_map 구조가 없다면 빈 딕셔너리로 초기화
            if "service_map" not in model_data:
                model_data["service_map"] = {}

            # 고유 요구 필수 파라미터 강제 주입     
            model_data["service_map"]["certkey"] = model_data.get("certkey", "")
            model_data["service_map"]["out"] = AgentConstants.JSON.lower()
            model_data["service_map"]["prodcd"] = model_data.get("prodcd", "")
            
            if model_data.get("area"):                  
                model_data["service_map"]["area"] = model_data["area"]
            if model_data.get("cnt"):                  
                model_data["service_map"]["cnt"] = model_data["cnt"]

            # 5. 부모 클래스(BaseAgent)의 규격에 맞게 다시 JSON 문자열로 직렬화하여 바인딩
            data_value_json = json.dumps(model_data["service_map"])

            # 부모의 동기식 HTTP 요청 처리 메서드 작동
            net_value_json = json.dumps(net_value)
            response_string = self._run(net_value_json, data_value_json)

            return response_string if response_string is not None else ""
        
        except Exception as e:
            raise e