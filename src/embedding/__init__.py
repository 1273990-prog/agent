"""
임베딩 클라이언트 패키지.
팩토리 함수를 통해 제공자(provider)를 교체할 수 있는 추상화 계층을 제공합니다.

사용 예:
    from embedding import create_embedding_client
    client = create_embedding_client(provider="gemini", api_key="YOUR_KEY")
    client = create_embedding_client(provider="bge")  # 로컬 BGE-M3
    vector = client.embed_text("삼성전자의 2024년 매출액")
"""
from embedding.base_client import BaseEmbeddingClient
from embedding.gemini_client import GeminiEmbeddingClient
from embedding.bge_client import BgeEmbeddingClient

# 제공자명 → 클라이언트 클래스 매핑 (확장 시 여기에 추가)
_PROVIDER_REGISTRY = {
    "gemini": GeminiEmbeddingClient,
    "bge": BgeEmbeddingClient,
    # "openai": OpenAIEmbeddingClient,  # 향후 추가
}


def create_embedding_client(provider: str = "gemini", **kwargs) -> BaseEmbeddingClient:
    """
    임베딩 클라이언트 팩토리 함수.
    provider 문자열만 바꾸면 소비자 코드 변경 없이 임베딩 모델을 교체할 수 있습니다.

    Args:
        provider: 임베딩 제공자 이름 ("gemini", "bge" 등)
        **kwargs: 제공자별 초기화 인자 (예: api_key)
                  BGE는 로컬 모델이므로 api_key 없이 호출 가능

    Returns:
        BaseEmbeddingClient 구현체 인스턴스

    Raises:
        ValueError: 지원하지 않는 provider를 지정한 경우
    """
    client_class = _PROVIDER_REGISTRY.get(provider.lower())
    if client_class is None:
        supported = ", ".join(_PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"[오류] 지원하지 않는 임베딩 제공자입니다: '{provider}'. "
            f"지원 목록: {supported}"
        )
    return client_class(**kwargs)


__all__ = [
    "BaseEmbeddingClient",
    "GeminiEmbeddingClient",
    "BgeEmbeddingClient",
    "create_embedding_client",
]
