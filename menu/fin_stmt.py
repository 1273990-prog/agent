import sys
import os
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


def search_financial_data(
    query: str,
    corp_name: Optional[str] = None,
    bsns_year: Optional[str] = None,
    account_nm: Optional[str] = None,
    top_k: int = 10,
    embedding_provider: str = "bge"
) -> List[Dict[str, Any]]:
    """자연어 질문을 임베딩하여 fin_stmt_embedding에서 유사한 재무제표 데이터를 검색합니다."""

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
        print(f"[오류] 쿼리 임베딩 실패: {e}")
        return []

    db_net_value = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "action": AgentConstants.SELECT
    }

    try:
        db_conn = DbConn(json.dumps(db_net_value))
        search_req = {
            "query_key": "SEARCH_FIN_STMT_EMBEDDING",
            "params": {
                "query_embedding": str(query_embedding),
                "corp_name": corp_name,
                "bsns_year": bsns_year,
                "account_nm": account_nm,
                "top_k": top_k
            }
        }
        db_conn.create_request(json.dumps(search_req))
        result_str = db_conn.create_response()
        results = json.loads(result_str)
    except Exception as e:
        print(f"[오류] 벡터 검색 실패: {e}")
        return []

    if not results or (len(results) == 1 and not results[0]):
        return []

    return results


def main():
    try:
        print("\n" + "=" * 60)
        print("        [ 재무제표 벡터 유사도 검색 ]")
        print("=" * 60)

        query = input("\n▶ 검색할 내용을 자연어로 입력하세요: ").strip()
        if not query:
            print("[오류] 검색어를 입력해야 합니다.")
            return

        print("\n  ── 조건 필터 (정확 매칭, Enter로 생략) ──")
        corp_name_input = input("  ▶ 기업명: ").strip() or None
        bsns_year_input = input("  ▶ 사업연도: ").strip() or None
        account_nm_input = input("  ▶ 계정과목: ").strip() or None

        top_k_input = input("\n▶ 결과 수 (기본값 10): ").strip()
        top_k = int(top_k_input) if top_k_input.isdigit() else 10

        provider_input = input("▶ 임베딩 모델 선택 (1: BGE-M3 로컬 [기본], 2: Gemini API): ").strip()
        provider = "gemini" if provider_input == "2" else "bge"

        # 적용된 필터 표시
        filters = []
        if corp_name_input:
            filters.append(f"기업명={corp_name_input}")
        if bsns_year_input:
            filters.append(f"연도={bsns_year_input}")
        if account_nm_input:
            filters.append(f"계정={account_nm_input}")
        filter_display = ", ".join(filters) if filters else "없음"

        print(f"\n[정보] 검색어: \"{query}\" | 조건 필터: {filter_display}")
        print("[정보] 검색 중...")

        results = search_financial_data(
            query=query,
            corp_name=corp_name_input,
            bsns_year=bsns_year_input,
            account_nm=account_nm_input,
            top_k=top_k,
            embedding_provider=provider
        )

        if not results:
            print("\n[결과 없음] 검색 결과가 없습니다.")
            return

        print("\n" + "=" * 100)
        print(f"  검색어: \"{query}\" | 필터: {filter_display} | 모델: {provider.upper()} | 결과: {len(results)}건")
        print("-" * 100)
        print(f"{'순위':^4} | {'기업명':^12} | {'연도':^6} | {'계정과목':^20} | {'유사도':^8} | 문장 (요약)")
        print("-" * 100)

        for idx, r in enumerate(results, 1):
            corp = str(r.get("corp_name", ""))[:12]
            year = str(r.get("bsns_year", ""))
            acct = str(r.get("account_nm", ""))[:20]
            sim = r.get("similarity", 0)
            doc = str(r.get("document_text", ""))[:50]
            sim_display = f"{float(sim):.4f}" if sim else "N/A"
            print(f"{idx:^4} | {corp:^12} | {year:^6} | {acct:^20} | {sim_display:^8} | {doc}...")

        print("=" * 100 + "\n")

    except Exception as e:
        print(f"[오류] 검색 중 예외가 발생했습니다: {e}")


if __name__ == "__main__":
    main()
