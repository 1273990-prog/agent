"""
재무제표 벡터화 배치 스크립트.
fin_stmt_info 테이블의 기존 데이터를 자연어 문장으로 변환한 뒤,
임베딩 벡터를 생성하여 fin_stmt_embedding 테이블에 저장합니다.

사용법:
    python fin_stmt_vectorizer.py
"""
import sys
import os
import io
import json
from typing import Dict, Any, List, Optional
from decimal import Decimal

# Windows CP949 콘솔 유니코드 출력 처리
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 'src' 디렉터리를 Python 검색 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))  # src/common
src_dir = os.path.abspath(os.path.join(current_dir, '..'))  # src

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from common.constants import AgentConstants
from common.utils import AgentUtils
from common.db_conn import DbConn
from embedding import create_embedding_client


# ============================================================
#  유틸리티: 금액 포맷팅
# ============================================================

def _format_amount(amount_value: Any) -> str:
    """
    숫자 금액을 콤마 구분 문자열로 변환합니다.
    예: 300870219000000 → "300,870,219,000,000"
    """
    if amount_value is None:
        return "0"
    try:
        num = Decimal(str(amount_value).replace(",", "").strip())
        # 정수인 경우 소수점 제거
        if num == num.to_integral_value():
            return f"{int(num):,}"
        return f"{num:,}"
    except Exception:
        return str(amount_value)


# ============================================================
#  핵심 함수 1: 자연어 문장 생성
# ============================================================

def build_document_text(row: Dict[str, Any]) -> str:
    """
    fin_stmt_info 레코드를 사람이 읽을 수 있는 자연어 문장으로 변환합니다.

    생성 형식:
        {기업명}의 {사업연도}년 {재무제표유형}에 따르면,
        {계정과목명}({상세}) 항목은 {금액}원입니다.
        (재무제표구분: {연결/별도}, 보고서: 사업보고서)

    Args:
        row: SELECT_FIN_STMT_FOR_VECTORIZE 쿼리 결과의 한 행

    Returns:
        임베딩용 자연어 문장 문자열
    """
    corp_name = str(row.get("corp_name", "")).strip() or "알 수 없는 기업"
    bsns_year = str(row.get("bsns_year", "")).strip() or "미상"
    sj_nm = str(row.get("sj_nm", "")).strip() or "재무제표"
    account_nm = str(row.get("account_nm", "")).strip() or "미분류 항목"
    account_detail = str(row.get("account_detail", "")).strip()
    thstrm_amount = row.get("thstrm_amount", 0)
    fs_nm = str(row.get("fs_nm", "")).strip() or "재무제표"

    # 계정과목 상세가 유효한 경우 괄호로 부연
    if account_detail and account_detail not in ("-", "", "None", "null"):
        account_display = f"{account_nm}({account_detail})"
    else:
        account_display = account_nm

    formatted_amount = _format_amount(thstrm_amount)

    document = (
        f"{corp_name}의 {bsns_year}년 {sj_nm}에 따르면, "
        f"{account_display} 항목은 {formatted_amount}원입니다. "
        f"(재무제표구분: {fs_nm}, 보고서: 사업보고서)"
    )

    return document


# ============================================================
#  핵심 함수 2: 배치 벡터화 실행
# ============================================================

def vectorize_fin_stmt_data(
    batch_size: int = 10,
    embedding_provider: str = "bge"
) -> Dict[str, Any]:
    """
    아직 벡터화되지 않은 fin_stmt_info 레코드를 일괄 임베딩하여
    fin_stmt_embedding 테이블에 저장합니다.

    Args:
        batch_size: 한 번에 처리 및 DB 커밋할 데이터 단위 (기본값 10건)
        embedding_provider: 임베딩 제공자 ("bge": 로컬 BGE-M3, "gemini": Gemini API)

    Returns:
        처리 결과 요약 딕셔너리
    """
    print("\n" + "=" * 80)
    print("        [ 재무제표 벡터화 배치 스크립트 ]")
    print("=" * 80)

    # 1. 설정 로드
    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return {"total_processed": 0, "total_skipped": 0, "status": "error"}

    # 2. 임베딩 클라이언트 생성 (프로바이더별 분기)
    try:
        embed_client = _create_embed_client(embedding_provider, config)
        print(f"  [초기화] 임베딩 모델: {embed_client.model_name} (차원: {embed_client.dimension})")
    except Exception as e:
        print(f"[오류] 임베딩 클라이언트 초기화 실패: {e}")
        return {"total_processed": 0, "total_skipped": 0, "status": "error"}

    # 3. 미벡터화 데이터 조회
    db_net_value_select = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "action": AgentConstants.SELECT
    }

    try:
        db_conn = DbConn(json.dumps(db_net_value_select))
        select_req = {
            "query_key": "SELECT_FIN_STMT_FOR_VECTORIZE",
            "params": {}
        }
        db_conn.create_request(json.dumps(select_req))
        result_str = db_conn.create_response()
        rows = json.loads(result_str)
    except Exception as e:
        print(f"[오류] 미벡터화 데이터 조회 실패: {e}")
        return {"total_processed": 0, "total_skipped": 0, "status": "error"}

    # 빈 결과 또는 빈 딕셔너리만 반환된 경우
    if not rows or (len(rows) == 1 and not rows[0]):
        print("\n  [완료] 벡터화할 신규 데이터가 없습니다. 모든 데이터가 이미 처리되었습니다.")
        return {"total_processed": 0, "total_skipped": 0, "status": "success"}

    total_rows = len(rows)
    print(f"\n  [조회] 미벡터화 대상 레코드: 총 {total_rows}건")

    # 4. 자연어 문장 생성
    documents = []
    valid_rows = []
    skipped = 0

    for row in rows:
        try:
            doc_text = build_document_text(row)
            documents.append(doc_text)
            valid_rows.append(row)
        except Exception as e:
            print(f"  [건너뜀] 문장 생성 실패 (rule_no: {row.get('rule_no', '?')}): {e}")
            skipped += 1

    if not documents:
        print("[경고] 유효한 문장이 하나도 생성되지 않았습니다.")
        return {"total_processed": 0, "total_skipped": skipped, "status": "error"}

    total_valid = len(documents)
    total_batches = (total_valid + batch_size - 1) // batch_size
    print(f"  [문장 생성 완료] 유효: {total_valid}건, 건너뜀: {skipped}건 (총 {total_batches}개 배치 예정)")

    # 5. 배치 단위 순차 임베딩 & DB 즉시 커밋
    print(f"\n  [{embedding_provider.upper()} 배치 실행] 배치 크기: {batch_size}건 단위 즉시 DB 커밋")

    db_net_value_insert = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "action": AgentConstants.INSERT
    }

    total_inserted = 0

    for b_idx in range(0, total_valid, batch_size):
        batch_num = (b_idx // batch_size) + 1
        b_rows = valid_rows[b_idx:b_idx + batch_size]
        b_docs = documents[b_idx:b_idx + batch_size]

        pct = ((b_idx + len(b_docs)) / total_valid) * 100
        print(f"  [배치 {batch_num}/{total_batches}] {len(b_docs)}건 임베딩 진행 중... (누적: {total_inserted}/{total_valid}건, {pct:.1f}%)")

        try:
            b_embs = embed_client.embed_batch(b_docs, batch_size=len(b_docs))
        except Exception as e:
            print(f"  [오류] 배치 {batch_num} 임베딩 중 예외 발생 (건너뜀): {e}")
            continue

        insert_params = []
        for row, doc_text, embedding in zip(b_rows, b_docs, b_embs):
            embedding_str = str(embedding)
            insert_params.append({
                "rule_no": AgentUtils.get_rule_no(),
                "rel_no": str(row.get("rule_no", "")),
                "corp_no": str(row.get("corp_no", "")),
                "corp_name": str(row.get("corp_name", "")),
                "bsns_year": str(row.get("bsns_year", "")),
                "sj_div": str(row.get("sj_div", "")),
                "account_nm": str(row.get("account_nm", "")),
                "document_text": doc_text,
                "embedding": embedding_str
            })

        if insert_params:
            try:
                db_conn_insert = DbConn(json.dumps(db_net_value_insert))
                insert_req = {
                    "query_key": "INSERT_FIN_STMT_EMBEDDING",
                    "params": insert_params
                }
                db_conn_insert.create_request(json.dumps(insert_req))
                db_conn_insert.create_response()
                total_inserted += len(insert_params)
            except Exception as e:
                print(f"  [오류] 배치 {batch_num} DB 저장 중 예외 발생: {e}")

    print(f"\n  [DB 저장 완료] fin_stmt_embedding 테이블에 총 {total_inserted}/{total_valid}건 저장 성공!")

    summary = {
        "total_processed": total_inserted,
        "total_skipped": skipped,
        "status": "success" if total_inserted > 0 else "error"
    }

    print("\n" + "=" * 80)
    print(f"  [최종 결과] 처리: {summary['total_processed']}건 | 건너뜀: {summary['total_skipped']}건 | 상태: {summary['status']}")
    print("=" * 80 + "\n")

    return summary


# ============================================================
#  핵심 함수 3: 벡터 유사도 검색 (내부 함수)
# ============================================================

def search_financial_data(
    query: str,
    corp_no: Optional[str] = None,
    top_k: int = 5,
    embedding_provider: str = "bge"
) -> List[Dict[str, Any]]:
    """
    자연어 질문을 임베딩하여 fin_stmt_embedding에서 유사한 재무제표 데이터를 검색합니다.

    Args:
        query: 자연어 검색 질의 (예: "삼성전자 2024년 매출액")
        corp_no: 특정 기업으로 제한할 corp_no (None이면 전체 검색)
        top_k: 반환할 최대 결과 수
        embedding_provider: 임베딩 제공자 ("bge": 로컬 BGE-M3, "gemini": Gemini API)

    Returns:
        유사도 순으로 정렬된 결과 딕셔너리 리스트
        각 항목: {"rule_no", "corp_name", "bsns_year", "account_nm", "document_text", "similarity"}
    """
    # 1. 설정 로드 및 임베딩 클라이언트 생성
    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return []

    try:
        embed_client = _create_embed_client(embedding_provider, config)
    except Exception as e:
        print(f"[오류] 임베딩 클라이언트 초기화 실패: {e}")
        return []

    # 2. 검색 쿼리 임베딩 (RETRIEVAL_QUERY task type)
    try:
        query_embedding = embed_client.embed_query(query)
    except Exception as e:
        print(f"[오류] 쿼리 임베딩 실패: {e}")
        return []

    # 3. 벡터 유사도 검색 실행
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
                "corp_no": corp_no,
                "top_k": top_k
            }
        }
        db_conn.create_request(json.dumps(search_req))
        result_str = db_conn.create_response()
        results = json.loads(result_str)

    except Exception as e:
        print(f"[오류] 벡터 검색 실패: {e}")
        return []

    # 빈 결과 처리
    if not results or (len(results) == 1 and not results[0]):
        return []

    return results


# ============================================================
#  CLI 진입점
# ============================================================

def _create_embed_client(provider: str, config: Dict[str, Any]):
    """
    프로바이더에 따라 임베딩 클라이언트를 생성합니다.
    BGE는 로컬 모델이므로 API 키 없이, Gemini는 API 키를 사용합니다.

    Args:
        provider: 임베딩 제공자 ("bge", "gemini")
        config: agent_key.json 설정 딕셔너리

    Returns:
        BaseEmbeddingClient 구현체 인스턴스

    Raises:
        ValueError: Gemini 선택 시 API 키가 없는 경우
    """
    if provider == "bge":
        return create_embedding_client(provider="bge")
    elif provider == "gemini":
        gemini_api_key = config.get("gemini_api_key", "")
        if not gemini_api_key:
            raise ValueError("agent_key.json에 'gemini_api_key'가 설정되어 있지 않습니다.")
        return create_embedding_client(provider="gemini", api_key=gemini_api_key)
    else:
        raise ValueError(f"지원하지 않는 임베딩 제공자: {provider}")


def main():
    print("\n" + "=" * 55)
    print("        [ 재무제표 벡터화 스크립트 ]")
    print("=" * 55)
    print("  1. 전체 벡터화 실행 (미처리 데이터)")
    print("  2. 벡터 검색 테스트")
    print("=" * 55)
    choice = input("원하는 작업 번호를 선택하세요 (1/2): ").strip()

    # 프로바이더 선택 (공통)
    provider_input = input("▶ 임베딩 모델 선택 (1: BGE-M3 로컬 [기본], 2: Gemini API): ").strip()
    provider = "gemini" if provider_input == "2" else "bge"

    if choice == "1":
        batch_input = input("\n▶ 배치 크기 (기본값 100): ").strip()
        batch_size = int(batch_input) if batch_input.isdigit() else 100
        vectorize_fin_stmt_data(batch_size=batch_size, embedding_provider=provider)

    elif choice == "2":
        query = input("\n▶ 검색할 내용을 자연어로 입력하세요: ").strip()
        if not query:
            print("[오류] 검색어를 입력해야 합니다.")
            return

        top_k_input = input("▶ 결과 수 (기본값 5): ").strip()
        top_k = int(top_k_input) if top_k_input.isdigit() else 5

        results = search_financial_data(query=query, top_k=top_k, embedding_provider=provider)

        if not results:
            print("\n[결과 없음] 검색 결과가 없습니다.")
            return

        print("\n" + "=" * 100)
        print(f"  검색어: \"{query}\" | 모델: {provider.upper()} | 결과: {len(results)}건")
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

    else:
        print("\n[오류] 잘못된 선택입니다. 1 또는 2를 입력하세요.")


if __name__ == "__main__":
    main()
