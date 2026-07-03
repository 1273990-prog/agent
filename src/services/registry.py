from typing import Dict, Type, Optional
from services.base_service import BaseService

# A global dictionary holding all registered services
_SERVICE_REGISTRY: Dict[str, Type[BaseService]] = {}

def register_service(name: str):
    def decorator(cls: Type[BaseService]):
        try:
            upper_name = name.upper()
            if upper_name in _SERVICE_REGISTRY:
                raise ValueError(f"Service '{name}' is already registered.")
            _SERVICE_REGISTRY[upper_name] = cls
            return cls
        except Exception as e:
            print(f"Failed to register service: {e}")
            raise e
    return decorator

def get_registered_service(name: str) -> Optional[Type[BaseService]]:
    if not isinstance(name, str):          
        return None                        
    return _SERVICE_REGISTRY.get(name.upper())  