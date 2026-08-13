from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingClient(ABC):
    """
    임베딩 클라이언트 추상 기반 클래스.
    모든 임베딩 제공자(Gemini, OpenAI 등)는 이 인터페이스를 구현합니다.
    제공자를 교체할 때 소비자 코드 변경 없이 구현체만 바꿀 수 있습니다.
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """임베딩 벡터 차원 수를 반환합니다."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """사용 중인 모델명을 반환합니다."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        단일 텍스트를 문서용 임베딩 벡터로 변환합니다.
        저장(document) 용도의 task type을 사용합니다.

        Args:
            text: 임베딩할 텍스트 문자열

        Returns:
            float 리스트 형태의 임베딩 벡터
        """
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        단일 텍스트를 검색 쿼리용 임베딩 벡터로 변환합니다.
        검색(query) 용도의 task type을 사용합니다.

        Args:
            text: 검색 질의 텍스트

        Returns:
            float 리스트 형태의 임베딩 벡터
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        다수의 텍스트를 배치 단위로 임베딩합니다.

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 한 번에 처리할 텍스트 수 (API rate limit 고려)

        Returns:
            각 텍스트에 대응하는 임베딩 벡터 리스트
        """
        pass
