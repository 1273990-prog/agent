from datetime import datetime
from typing import Optional, Dict, Any, Final
import uuid

class AgentUtils:
    def get_rule_no() -> str:
        rule_type = "00"
        
        # 1. YYYYMMDDHH24MISSMS 형태의 현재 시간 포맷팅 (밀리초 3자리 포함)
        # %f는 마이크로초(6자리)를 리턴하므로 끝의 3자리를 잘라 밀리초로 만듭니다.
        now = datetime.now()
        time_str = now.strftime("%Y%m%d%H%M%S") + now.strftime("%f")[:3]
    
        # 2. UUID 생성 후 하이픈('-') 제거
        uuid_str = str(uuid.uuid4()).replace("-", "")
    
        # 3. 시간 + 타입코드 + UUID 결합
        rule_no = time_str + rule_type + uuid_str
    
        return rule_no
    
    def object_value(self, model: Dict[str, Any], obj_type: Dict[str, Any]) -> str: return ""
    def array_value(self, model: Dict[str, Any]) -> str: return ""
    def array_obj_value(self, model: Dict[str, Any], obj_type: Dict[str, Any]) -> str: return ""