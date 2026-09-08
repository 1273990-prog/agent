import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from common.fin_stmt_vectorizer import search_financial_data


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
