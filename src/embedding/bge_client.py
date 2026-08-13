"""
BGE-M3 로컬 임베딩 클라이언트.
HuggingFace sentence-transformers를 사용하여 로컬에서 임베딩을 생성합니다.
API 호출이 없으므로 rate limit 제약 없이 고속 배치 처리가 가능합니다.

필수 패키지 설치:
    pip install sentence-transformers
"""
import torch
from typing import List, Optional

from embedding.base_client import BaseEmbeddingClient


class BgeEmbeddingClient(BaseEmbeddingClient):
    """
    BAAI/bge-m3 기반 로컬 임베딩 클라이언트.
    다국어(한국어 포함) 지원, 1024차원 Dense 벡터를 생성합니다.
    GPU가 있으면 자동으로 사용하고, 없으면 CPU로 동작합니다.

    특징:
        - 로컬 실행: API 키 불필요, rate limit 없음
        - 다국어 지원: 한국어 재무제표 텍스트에 적합
        - Dense/Sparse/ColBERT 멀티 벡터 중 Dense 벡터만 사용
    """

    _DEFAULT_MODEL = "BAAI/bge-m3"
    _DIMENSION = 1024
    _MAX_SEQ_LENGTH = 8192

    # BGE 모델 권장 검색 쿼리 프리픽스
    _QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        use_fp16: bool = True,
        **kwargs
    ):
        """
        BGE-M3 임베딩 클라이언트를 초기화합니다.

        Args:
            model_name: HuggingFace 모델 ID (기본값: BAAI/bge-m3)
            device: 실행 디바이스 ("cuda", "cpu", None이면 자동 감지)
            use_fp16: GPU 사용 시 FP16 반정밀도 활성화 (메모리 절약)
            **kwargs: 추가 키워드 인자 (팩토리 호환용, api_key 등 무시)
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "[오류] sentence-transformers 패키지가 설치되지 않았습니다.\n"
                "       설치: pip install sentence-transformers"
            )

        self._model_id = model_name or self._DEFAULT_MODEL

        # 디바이스 자동 감지 (CUDA → MPS(Apple Silicon) → CPU)
        if device is None:
            if torch.cuda.is_available():
                self._device = "cuda"
            elif torch.backends.mps.is_available():
                self._device = "mps"
            else:
                self._device = "cpu"
        else:
            self._device = device

        # FP16은 GPU에서만 사용
        effective_fp16 = use_fp16 and self._device == "cuda"

        print(f"  [BGE 초기화] 모델: {self._model_id}")
        print(f"  [BGE 초기화] 디바이스: {self._device} | FP16: {effective_fp16}")
        print(f"  [BGE 초기화] 모델 로딩 중... (최초 실행 시 다운로드)")

        self._model = SentenceTransformer(
            self._model_id,
            device=self._device,
            trust_remote_code=True
        )

        if effective_fp16:
            self._model.half()

        self._model.max_seq_length = self._MAX_SEQ_LENGTH

        print(f"  [BGE 초기화] 로딩 완료 (차원: {self._DIMENSION})")

    @property
    def dimension(self) -> int:
        return self._DIMENSION

    @property
    def model_name(self) -> str:
        return self._model_id

    def embed_text(self, text: str) -> List[float]:
        """
        단일 텍스트를 문서용 임베딩 벡터로 변환합니다.
        문서 저장 시에는 프리픽스 없이 원문 그대로 임베딩합니다.
        """
        embedding = self._model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return embedding.tolist()

    def embed_query(self, text: str) -> List[float]:
        """
        단일 텍스트를 검색 쿼리용 임베딩 벡터로 변환합니다.
        BGE 권장 프리픽스를 추가하여 검색 정확도를 높입니다.
        """
        query_text = self._QUERY_PREFIX + text
        embedding = self._model.encode(
            query_text,
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return embedding.tolist()

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        다수의 텍스트를 배치 단위로 문서용 임베딩합니다.
        로컬 실행이므로 API rate limit 없이 고속 배치 처리가 가능합니다.

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 한 번에 GPU/CPU에 올릴 배치 크기 (기본값 32)

        Returns:
            각 텍스트에 대응하는 임베딩 벡터 리스트
        """
        if not texts:
            return []

        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 10
        )
        return embeddings.tolist()
