import sys
import os
import re
import json
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from common.constants import AgentConstants
from common.utils import AgentUtils
from common.db_conn import DbConn
from embedding import create_embedding_client


def _create_embed_client(provider: str, config: Dict[str, Any]):
    """프로바이더에 따라 임베딩 클라이언트를 생성합니다."""
    if provider == "bge":
        return create_embedding_client(provider="bge")
    elif provider == "gemini":
        gemini_api_key = config.get("gemini_api_key", "")
        if not gemini_api_key:
            raise ValueError("agent_key.json에 'gemini_api_key'가 설정되어 있지 않습니다.")
        return create_embedding_client(provider="gemini", api_key=gemini_api_key)
    else:
        raise ValueError(f"지원하지 않는 임베딩 제공자: {provider}")


def search_trade_trend_data(
    query: str,
    period: Optional[str] = None,
    item: Optional[str] = None,
    region: Optional[str] = None,
    contest_type: Optional[str] = None,
    top_k: int = 10,
    embedding_provider: str = "bge"
) -> List[Dict[str, Any]]:
    """자연어 질문을 임베딩하여 trade_trend_detail에서 유사한 수출입동향 데이터를 검색합니다."""

    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return []

    try:
        embed_client = _create_embed_client(embedding_provider, config)
    except Exception as e:
        print(f"[오류] 임베딩 클라이언트 초기화 실패: {e}")
        return []

    try:
        query_embedding = embed_client.embed_query(query)
    except Exception as e:
        print(f"[오류] 검색 쿼리 임베딩 실패: {e}")
        return []

    db_net_value = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "action": AgentConstants.SELECT
    }

    # period 정규화
    norm_period = None
    if period:
        p_str = str(period).strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}$', p_str):
            norm_period = p_str
        elif re.match(r'^\d{4}-\d{2}$', p_str):
            norm_period = f"{p_str}-01"

    try:
        db_conn = DbConn(json.dumps(db_net_value))
        search_req = {
            "query_key": "SEARCH_TRADE_TREND_DETAIL_EMBEDDING",
            "params": {
                "query_embedding": str(query_embedding),
                "period": norm_period,
                "item": item,
                "region": region,
                "contest_type": contest_type,
                "top_k": top_k
            }
        }
        db_conn.create_request(json.dumps(search_req))
        result_str = db_conn.create_response()
        results = json.loads(result_str)
    except Exception as e:
        print(f"[오류] 벡터 유사도 검색 실패: {e}")
        return []

    if not results or (len(results) == 1 and not results[0]):
        return []

    return results


def main():
    try:
        print("\n" + "=" * 60)
        print("        [ 수출입동향 벡터 유사도 검색 ]")
        print("=" * 60)

        query = input("\n▶ 검색할 내용을 자연어로 입력하세요: ").strip()
        if not query:
            print("[오류] 검색어를 입력해야 합니다.")
            return

        print("\n  ── 조건 필터 (정확 매칭, Enter로 생략) ──")
        period_input = input("  ▶ 대상 기간 (예: 2026-07): ").strip() or None
        item_input = input("  ▶ 품목 (예: 반도체, 자동차): ").strip() or None
        region_input = input("  ▶ 지역 (예: 중국, 미국): ").strip() or None
        contest_type_input = input("  ▶ 유형 (narrative/table): ").strip() or None

        top_k_input = input("\n▶ 결과 수 (기본값 10): ").strip()
        top_k = int(top_k_input) if top_k_input.isdigit() else 10

        provider_input = input("▶ 임베딩 모델 선택 (1: BGE-M3 로컬 [기본], 2: Gemini API): ").strip()
        provider = "gemini" if provider_input == "2" else "bge"

        # 적용된 필터 표시
        filters = []
        if period_input:
            filters.append(f"기간={period_input}")
        if item_input:
            filters.append(f"품목={item_input}")
        if region_input:
            filters.append(f"지역={region_input}")
        if contest_type_input:
            filters.append(f"유형={contest_type_input}")
        filter_display = ", ".join(filters) if filters else "없음"

        print(f"\n[정보] 검색어: \"{query}\" | 조건 필터: {filter_display}")
        print("[정보] 검색 중...")

        results = search_trade_trend_data(
            query=query,
            period=period_input,
            item=item_input,
            region=region_input,
            contest_type=contest_type_input,
            top_k=top_k,
            embedding_provider=provider
        )

        if not results:
            print("\n[결과 없음] 검색 결과가 없습니다.")
            return

        print("\n" + "=" * 110)
        print(f"  검색어: \"{query}\" | 필터: {filter_display} | 모델: {provider.upper()} | 결과: {len(results)}건")
        print("-" * 110)
        print(f"{'순위':^4} | {'대상기간':^10} | {'문서제목':^24} | {'섹션/분류':^28} | {'유사도':^8} | 본문 미리보기")
        print("-" * 110)

        for idx, r in enumerate(results, 1):
            p = str(r.get("period", ""))[:10]
            title = str(r.get("doc_title", ""))[:24]
            sec = str(r.get("trade_trend_section", ""))[:28]
            sim = r.get("similarity", 0)
            text = str(r.get("trade_trend_text", "")).replace("\n", " ")[:45]
            sim_display = f"{float(sim):.4f}" if sim else "N/A"
            print(f"{idx:^4} | {p:^10} | {title:<24} | {sec:<28} | {sim_display:^8} | {text}...")

        print("=" * 110 + "\n")

    except Exception as e:
        print(f"[오류] 검색 중 예외가 발생했습니다: {e}")


if __name__ == "__main__":
    main()
