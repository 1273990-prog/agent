"""
수출입동향 청크 벡터화 배치 스크립트.
trade_trend_detail 테이블의 미벡터화 청크(embedding IS NULL)를 조회하여
BGE-M3 또는 Gemini 임베딩 모델로 1024차원 벡터를 생성한 후,
trade_trend_detail 테이블의 embedding 컬럼에 직접 업데이트(UPDATE)합니다.

참고: fin_stmt_vectorizer.py 구조를 기반으로 작성되었습니다.

사용법:
    python src/common/trade_trend_vectorizer.py
"""
import sys
import os
import io
import json
import re
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

# Windows CP949 콘솔 유니코드 출력 처리
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
elif hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# 'src' 디렉터리를 Python 검색 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))  # src/common
src_dir = os.path.abspath(os.path.join(current_dir, '..'))  # src
project_root = os.path.abspath(os.path.join(src_dir, '..')) # agent

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from common.constants import AgentConstants
from common.utils import AgentUtils
from common.db_conn import DbConn
from embedding import create_embedding_client


# ============================================================
#  1. 임베딩용 시맨틱 텍스트 구성 함수
# ============================================================

def build_document_text(row: Dict[str, Any]) -> str:
    """
    trade_trend_detail 레코드의 trade_trend_text 컬럼 본문을 그대로 반환하여
    embedding 컬럼에 직접 임베딩하도록 합니다.

    Args:
        row: SELECT_TRADE_TREND_DETAIL_FOR_VECTORIZE 쿼리 결과의 한 행

    Returns:
        임베딩 대상 원문 텍스트 (trade_trend_text)
    """
    return str(row.get("trade_trend_text", "")).strip()


# ============================================================
#  2. 배치 벡터화 실행 함수
# ============================================================

def vectorize_trade_trend_data(
    batch_size: int = 50,
    embedding_provider: str = "bge",
    loop_until_done: bool = True
) -> Dict[str, Any]:
    """
    아직 벡터화되지 않은 trade_trend_detail 레코드(embedding IS NULL)를 일괄 임베딩하여
    trade_trend_detail.embedding 컬럼에 업데이트합니다.

    Args:
        batch_size: 한 번에 임베딩 및 DB 커밋할 데이터 단위 (기본값 50건)
        embedding_provider: 임베딩 제공자 ("bge": 로컬 BGE-M3, "gemini": Gemini API)
        loop_until_done: True인 경우 남은 미처리 데이터가 없을 때까지 무한 반복 수행

    Returns:
        처리 결과 요약 딕셔너리
    """
    print("\n" + "=" * 90)
    print("        [ 수출입동향 데이터 벡터화 배치 (trade_trend_vectorizer) ]")
    print("=" * 90)

    # 1. 설정 로드
    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return {"total_processed": 0, "total_skipped": 0, "status": "error"}

    # 2. 임베딩 클라이언트 생성
    try:
        embed_client = _create_embed_client(embedding_provider, config)
        print(f"  [초기화] 임베딩 모델: {embed_client.model_name} (차원: {embed_client.dimension})")
    except Exception as e:
        print(f"[오류] 임베딩 클라이언트 초기화 실패: {e}")
        return {"total_processed": 0, "total_skipped": 0, "status": "error"}

    db_net_select = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "action": AgentConstants.SELECT
    }

    db_net_update = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "action": AgentConstants.UPDATE
    }

    grand_total_updated = 0
    grand_total_skipped = 0
    iteration = 0

    while True:
        iteration += 1
        print(f"\n--- [회차 {iteration}] 미벡터화 청크 조회 중... ---")

        # 3. 미벡터화 청크 조회 (embedding IS NULL)
        try:
            db_conn = DbConn(json.dumps(db_net_select))
            select_req = {
                "query_key": "SELECT_TRADE_TREND_DETAIL_FOR_VECTORIZE",
                "params": {}
            }
            db_conn.create_request(json.dumps(select_req))
            result_str = db_conn.create_response()
            rows = json.loads(result_str)
        except Exception as e:
            print(f"[오류] 미벡터화 데이터 조회 실패: {e}")
            break

        # 빈 결과 체크
        if not rows or (len(rows) == 1 and not rows[0]):
            print("\n  [완료] 벡터화할 신규 데이터가 없습니다. 모든 청크의 벡터화가 완료되었습니다.")
            break

        total_rows = len(rows)
        print(f"  [조회 완료] 미벡터화 대상: {total_rows}건 (누적 업데이트 성공: {grand_total_updated}건)")

        # 4. 시맨틱 텍스트 빌드
        documents = []
        valid_rows = []
        skipped = 0

        for row in rows:
            try:
                doc_text = build_document_text(row)
                if not doc_text.strip():
                    skipped += 1
                    continue
                documents.append(doc_text)
                valid_rows.append(row)
            except Exception as e:
                print(f"  [건너뜀] 텍스트 빌드 실패 (rule_no: {row.get('rule_no', '?')}): {e}")
                skipped += 1

        grand_total_skipped += skipped
        if not documents:
            print("[경고] 유효한 텍스트가 하나도 생성되지 않았습니다. 중단합니다.")
            break

        total_valid = len(documents)
        total_batches = (total_valid + batch_size - 1) // batch_size
        print(f"  [텍스트 준비 완료] 유효: {total_valid}건 (총 {total_batches}개 배치 진행)")

        # 5. 배치 단위 순차 임베딩 & DB UPDATE 커밋
        total_updated = 0

        for b_idx in range(0, total_valid, batch_size):
            batch_num = (b_idx // batch_size) + 1
            b_rows = valid_rows[b_idx:b_idx + batch_size]
            b_docs = documents[b_idx:b_idx + batch_size]

            pct = ((b_idx + len(b_docs)) / total_valid) * 100
            print(f"  [배치 {batch_num}/{total_batches}] {len(b_docs)}건 임베딩 생성 중... (진행률: {pct:.1f}%)")

            try:
                b_embs = embed_client.embed_batch(b_docs, batch_size=len(b_docs))
            except Exception as e:
                print(f"  [오류] 배치 {batch_num} 임베딩 생성 중 예외 발생 (건너뜀): {e}")
                continue

            update_params = []
            for row, embedding in zip(b_rows, b_embs):
                embedding_str = str(embedding)
                update_params.append({
                    "rule_no": str(row.get("rule_no", "")),
                    "embedding": embedding_str
                })

            if update_params:
                try:
                    db_conn_update = DbConn(json.dumps(db_net_update))
                    update_req = {
                        "query_key": "UPDATE_TRADE_TREND_DETAIL_EMBEDDING",
                        "params": update_params
                    }
                    db_conn_update.create_request(json.dumps(update_req))
                    db_conn_update.create_response()
                    total_updated += len(update_params)
                except Exception as e:
                    print(f"  [오류] 배치 {batch_num} DB 업데이트 중 예외 발생: {e}")

        grand_total_updated += total_updated
        print(f"  [회차 완료] 이번 회차 업데이트: {total_updated}/{total_valid}건 (누적 합계: {grand_total_updated}건)")

        if not loop_until_done:
            break

    summary = {
        "total_processed": grand_total_updated,
        "total_skipped": grand_total_skipped,
        "status": "success" if grand_total_updated > 0 else "done"
    }

    print("\n" + "=" * 90)
    print(f"  [최종 결과] 총 누적 업데이트: {summary['total_processed']}건 | 건너뜀: {summary['total_skipped']}건 | 상태: {summary['status']}")
    print("=" * 90 + "\n")

    return summary


# ============================================================
#  3. 벡터 유사도 검색 함수
# ============================================================

def search_trade_trend_data(
    query: str,
    period: Optional[str] = None,
    item: Optional[str] = None,
    region: Optional[str] = None,
    contest_type: Optional[str] = None,
    top_k: int = 5,
    embedding_provider: str = "bge"
) -> List[Dict[str, Any]]:
    """
    자연어 질문을 임베딩하여 trade_trend_detail에서 코사인 유사도가 가장 높은 청크를 검색합니다.
    기간(period), 품목(item), 지역(region), 유형(contest_type) 필터링을 지원합니다.

    Args:
        query: 자연어 검색 질의 (예: "2026년 7월 반도체 수출 실적과 메모리 고정가격")
        period: 특정 대상 기간 (예: "2026-07-01", None이면 전체 기간 검색)
        item: 특정 품목 필터 (예: "반도체", "자동차", None이면 전체 품목)
        region: 특정 지역 필터 (예: "중국", "미국", None이면 전체 지역)
        contest_type: 청크 유형 필터 ("narrative", "table", None이면 전체)
        top_k: 반환할 최대 결과 수 (기본값 5)
        embedding_provider: 임베딩 제공자 ("bge" 또는 "gemini")

    Returns:
        유사도 순으로 정렬된 검색 결과 리스트
    """
    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return []

    # 1. 임베딩 클라이언트 생성
    try:
        embed_client = _create_embed_client(embedding_provider, config)
    except Exception as e:
        print(f"[오류] 임베딩 클라이언트 초기화 실패: {e}")
        return []

    # 2. 검색 쿼리 임베딩
    try:
        query_embedding = embed_client.embed_query(query)
    except Exception as e:
        print(f"[오류] 검색 쿼리 임베딩 실패: {e}")
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


# ============================================================
#  4. 진행 현황 및 통계 조회 함수
# ============================================================

def get_vectorization_status():
    """DB 내의 수출입동향 전체 청크 수 및 벡터화 완료/미완료 현황을 조회하여 출력합니다."""
    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return

    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        conn = psycopg2.connect(
            host=config.get("db_host"),
            port=int(config.get("port", 5432)),
            database=config.get("database"),
            user=config.get("username"),
            password=config.get("password")
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT i.period, i.doc_title,
                   count(d.rule_no) as total_chunks,
                   count(CASE WHEN d.embedding IS NOT NULL THEN 1 END) as vectorized_cnt,
                   count(CASE WHEN d.embedding IS NULL THEN 1 END) as unvectorized_cnt
            FROM trade_trend_info i
            LEFT JOIN trade_trend_detail d ON i.rule_no = d.trade_trend_no
            GROUP BY i.rule_no, i.period, i.doc_title
            ORDER BY i.period ASC;
        """)
        rows = cur.fetchall()

        cur.execute("""
            SELECT count(*) as total,
                   count(CASE WHEN embedding IS NOT NULL THEN 1 END) as done,
                   count(CASE WHEN embedding IS NULL THEN 1 END) as pending
            FROM trade_trend_detail;
        """)
        tot = cur.fetchone()

        cur.close()
        conn.close()

        print("\n" + "=" * 95)
        print("        [ 수출입동향 벡터화 진행 현황 ]")
        print("=" * 95)
        print(f"{'대상 기간':^12} | {'문서 제목':^32} | {'전체':^8} | {'완료':^8} | {'미완료':^8} | 진행률")
        print("-" * 95)

        for r in rows:
            p = str(r["period"])[:10]
            t = str(r["doc_title"])[:32]
            tc = r["total_chunks"]
            vc = r["vectorized_cnt"]
            uv = r["unvectorized_cnt"]
            pct = (vc / tc * 100) if tc > 0 else 0.0
            print(f"{p:^12} | {t:<32} | {tc:^8d} | {vc:^8d} | {uv:^8d} | {pct:5.1f}%")

        print("-" * 95)
        total_cnt = tot["total"]
        done_cnt = tot["done"]
        pending_cnt = tot["pending"]
        overall_pct = (done_cnt / total_cnt * 100) if total_cnt > 0 else 0.0
        print(f"  ▶ 전체 청크: {total_cnt}건 | 완료: {done_cnt}건 | 미완료: {pending_cnt}건 (총 진행률: {overall_pct:.1f}%)")
        print("=" * 95 + "\n")

    except Exception as e:
        print(f"[오류] 진행 현황 조회 실패: {e}")


# ============================================================
#  5. 내부 유틸리티 및 메인 CLI 진입점
# ============================================================

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


def main():
    print("\n" + "=" * 65)
    print("        [ 수출입동향 벡터화 스크립트 (trade_trend_vectorizer) ]")
    print("=" * 65)
    print("  1. 전체 미벡터화 청크 일괄 벡터화 (Batch Vectorize)")
    print("  2. 벡터 유사도 검색 테스트 (Semantic Search Test)")
    print("  3. 벡터화 진행 현황 및 통계 조회")
    print("=" * 65)

    choice = input("원하는 작업 번호를 선택하세요 (1/2/3, 기본값 1): ").strip() or "1"

    if choice in ("1", "2"):
        provider_input = input("\n▶ 임베딩 모델 선택 (1: BGE-M3 로컬 [기본], 2: Gemini API): ").strip()
        provider = "gemini" if provider_input == "2" else "bge"

    if choice == "1":
        batch_input = input("\n▶ 배치 크기 (기본값 50): ").strip()
        batch_size = int(batch_input) if batch_input.isdigit() else 50
        vectorize_trade_trend_data(batch_size=batch_size, embedding_provider=provider)

    elif choice == "2":
        query = input("\n▶ 검색할 내용을 자연어로 입력하세요 (예: 7월 반도체 수출 실적): ").strip()
        if not query:
            print("[오류] 검색어를 입력해야 합니다.")
            return

        item_input = input("▶ 품목 필터 (선택, 예: 반도체, 자동차, 엔터=전체): ").strip()
        item = item_input if item_input else None

        region_input = input("▶ 지역 필터 (선택, 예: 중국, 미국, 엔터=전체): ").strip()
        region = region_input if region_input else None

        period_input = input("▶ 대상 기간 필터 (선택, 예: 2026-07, 엔터=전체): ").strip()
        period = period_input if period_input else None

        top_k_input = input("▶ 반환할 결과 수 (기본값 5): ").strip()
        top_k = int(top_k_input) if top_k_input.isdigit() else 5

        results = search_trade_trend_data(
            query=query,
            period=period,
            item=item,
            region=region,
            top_k=top_k,
            embedding_provider=provider
        )

        if not results:
            print("\n[결과 없음] 조건에 맞는 검색 결과가 없습니다.")
            return

        print("\n" + "=" * 110)
        print(f"  검색어: \"{query}\" | 모델: {provider.upper()} | 결과: {len(results)}건")
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

    elif choice == "3":
        get_vectorization_status()
    else:
        print("\n[오류] 잘못된 선택입니다. 1, 2, 3 중 하나를 입력하세요.")


if __name__ == "__main__":
    main()
