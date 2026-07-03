from typing import Optional
from services.base_service import BaseService
from services.registry import get_registered_service

class ServiceFactory:
    def create(service_type: str) -> Optional[BaseService]:
        try:
            # Retrieve class from dynamic registry
            service_class = get_registered_service(service_type)
            if not service_class:
                return None
                
            return service_class()
        except Exception as e:
            print(f"Failed to create service: {e}")
            raise e