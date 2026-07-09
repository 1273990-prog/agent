from datetime import datetime, timezone
from typing import Dict, Any
import sys
import os
import json
import uuid

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

class AgentUtils:
    def get_rule_no() -> str:
        rule_type = "00"
        
        # 1. YYYYMMDDHH24MISSMS 형태의 현재 시간 포맷팅 (밀리초 3자리 포함)
        # %f는 마이크로초(6자리)를 리턴하므로 끝의 3자리를 잘라 밀리초로 만듭니다.
        now = datetime.now(timezone.utc)
        time_str = now.strftime("%Y%m%d%H%M%S%f")[:-3]
    
        # 2. UUID 생성 후 하이픈('-') 제거
        uuid_str = str(uuid.uuid4()).replace("-", "")
    
        # 3. 시간 + 타입코드 + UUID 결합
        rule_no = time_str + rule_type + uuid_str
    
        return rule_no
    
    def load_config(config_file: str) -> Dict[str, Any]:
        """Loads configuration keys from agent_key.json located in the project root."""
        # Look for agent_key.json in the parent directory of 'src'
        config_path = os.path.abspath(os.path.join(current_dir, '..', '..', f'{config_file}'))
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[오류] 설정 파일을 읽는데 실패했습니다: {e}")
                return e
        else:
            print(f"[경고] 설정 파일({config_path})이 존재하지 않습니다.")
            return e