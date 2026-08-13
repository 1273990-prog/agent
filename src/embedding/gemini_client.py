import time
from typing import List, Optional

from google import genai

from embedding.base_client import BaseEmbeddingClient


class GeminiEmbeddingClient(BaseEmbeddingClient):
    """
    Google Gemini gemini-embedding-001 / gemini-embedding-2 기반 임베딩 클라이언트.
    문서 저장 시 RETRIEVAL_DOCUMENT, 검색 쿼리 시 RETRIEVAL_QUERY task type을 사용합니다.
    Google AI Studio 무료 플랜 및 429 쿼터 초과 시 자동 대체 모델(Fallback) 전환을 지원합니다.
    """

    # Gemini embedding 모델 후보 목록 (gemini-embedding-2 우선, gemini-embedding-001 대체)
    _MODEL_CANDIDATES = [
        "models/gemini-embedding-2",
        "models/gemini-embedding-001",
    ]
    _DIMENSION = 768
    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 2   # 일반 오류 재시도 대기시간(초)
    _REQUEST_DELAY = 4.1     # 무료 플랜 15 RPM 준수를 위한 요청 간 지연시간(초)

    def __init__(self, api_key: str):
        """
        Gemini 임베딩 클라이언트를 초기화합니다.

        Args:
            api_key: Google AI Studio에서 발급받은 Gemini API 키
        """
        if not api_key:
            raise ValueError("[오류] Gemini API 키가 비어 있습니다.")
        self._client = genai.Client(api_key=api_key)
        self._active_model_idx = 0

    @property
    def dimension(self) -> int:
        return self._DIMENSION

    @property
    def model_name(self) -> str:
        return self._MODEL_CANDIDATES[self._active_model_idx]

    def embed_text(self, text: str) -> List[float]:
        """단일 텍스트를 문서용(RETRIEVAL_DOCUMENT) 벡터로 임베딩합니다."""
        return self._embed_with_retry(text, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> List[float]:
        """단일 텍스트를 검색 쿼리용(RETRIEVAL_QUERY) 벡터로 임베딩합니다."""
        return self._embed_with_retry(text, task_type="RETRIEVAL_QUERY")

    def embed_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """
        다수의 텍스트를 배치 단위로 문서용 임베딩합니다.
        무료 플랜 15 RPM 한도를 준수하며 진행 상황을 표시합니다.

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 한 번에 처리할 배치 단위 (기본값 10)

        Returns:
            각 텍스트에 대응하는 임베딩 벡터 리스트
        """
        return self._embed_batch_with_retry(texts)

    def _embed_with_retry(self, text: str, task_type: str) -> List[float]:
        """재시도 및 429 쿼터 초과 시 대체 모델 자동 전환(Fallback)이 포함된 단일 텍스트 임베딩"""
        last_exception: Optional[Exception] = None

        # 현재 활성 모델부터 순서대로 대체 후보 모델 시도
        candidates = (
            self._MODEL_CANDIDATES[self._active_model_idx:] +
            self._MODEL_CANDIDATES[:self._active_model_idx]
        )

        for candidate in candidates:
            for attempt in range(1, self._MAX_RETRIES + 1):
                try:
                    result = self._client.models.embed_content(
                        model=candidate,
                        contents=text,
                        config={"task_type": task_type, "output_dimensionality": self._DIMENSION}
                    )
                    # 성공한 모델을 활성 모델로 업데이트
                    self._active_model_idx = self._MODEL_CANDIDATES.index(candidate)
                    return list(result.embeddings[0].values)
                except Exception as e:
                    last_exception = e
                    is_quota_error = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "Quota" in str(e)
                    if is_quota_error:
                        print(f"  [경고] 모델 ({candidate}) 일일 쿼터 초과/429 오류 발생. 대체 모델로 전환합니다.")
                        break  # 60초 대기하지 않고 즉시 다음 대체 모델 시도

                    delay = self._RETRY_BASE_DELAY * attempt
                    print(f"  [재시도] API 오류 발생 (모델: {candidate}, 시도 {attempt}/{self._MAX_RETRIES}), "
                          f"{delay}초 대기 후 재시도... (원인: {e})")
                    time.sleep(delay)

        if last_exception:
            print(f"  [오류] 모든 임베딩 모델 시도 실패: {last_exception}")
            raise last_exception

    def _embed_batch_with_retry(self, texts: List[str]) -> List[List[float]]:
        """
        무료 플랜(15 RPM) 안전 순차 임베딩.
        각 텍스트 호출 간 4.1초 지연을 보장하여 429 쿼터 초과를 방지합니다.
        """
        embeddings: List[List[float]] = []
        total = len(texts)

        for idx, t in enumerate(texts, 1):
            emb = self._embed_with_retry(t, task_type="RETRIEVAL_DOCUMENT")
            embeddings.append(emb)

            # 마지막 요청이 아니면 15 RPM 지연(4.1초) 적용
            if idx < total:
                time.sleep(self._REQUEST_DELAY)

        return embeddings



