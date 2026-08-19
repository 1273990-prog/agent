"""
수출입동향 PDF/JSON 로더 및 DB 적재 스크립트.
산업통상자원부 수출입동향 PDF 문서를 파싱/의미 단위 청킹(Semantic Chunking)하거나
정제된 JSON 청크 데이터를 읽어와 trade_trend_info(마스터) 및
trade_trend_detail(청크 상세) 테이블에 구조화하여 적재합니다.

참고: fin_stmt_loader.py 구조를 기반으로 작성되었습니다.
(벡터화는 추후 별도 스크립트에서 수행)

사용법:
    python src/common/trade_trend_loader.py
    python src/common/trade_trend_loader.py "src/250701_2025년 6월 수출입동향_3보_추가수정.pdf"
    python src/common/trade_trend_loader.py "src/trade_trend_chunks.json"
    python src/common/trade_trend_loader.py "src"
"""
import sys
import os
import io
import json
import re
import glob
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime, date

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

# Add 'src' directory to Python search path if not already present
current_dir = os.path.dirname(os.path.abspath(__file__))  # src/common
src_dir = os.path.abspath(os.path.join(current_dir, '..')) # src
project_root = os.path.abspath(os.path.join(src_dir, '..')) # agent (프로젝트 루트)

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from common.constants import AgentConstants
from common.utils import AgentUtils
from common.db_conn import DbConn

# PDF 파서 라이브러리 import (PyMuPDF 우선, pypdf 보조)
try:
    import pymupdf  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


# ============================================================
#  품목 및 지역 매핑 사전 (20대 주력 품목 & 9대 주요 지역)
# ============================================================

ITEM_MAP: Dict[str, str] = {
    "반도체": "반도체",
    "자동차": "자동차",
    "차부품": "자동차부품",
    "자동차부품": "자동차부품",
    "선박": "선박",
    "무선통신": "무선통신기기",
    "무선통신기기": "무선통신기기",
    "컴퓨터": "컴퓨터",
    "컴퓨터SSD": "컴퓨터(SSD)",
    "디스플레이": "디스플레이",
    "철강": "철강",
    "일반기계": "일반기계",
    "석유제품": "석유제품",
    "석유화학": "석유화학",
    "이차전지": "이차전지",
    "가전": "가전",
    "섬유": "섬유",
    "농수산식품": "농수산식품",
    "농수산": "농수산식품",
    "화장품": "화장품",
    "전기기기": "전기기기",
    "생활용품": "생활용품",
    "비철금속": "비철금속",
    "바이오헬스": "바이오헬스",
    "바이오": "바이오헬스"
}

REGION_MAP: Dict[str, str] = {
    "중국": "중국",
    "미국": "미국",
    "아세안": "아세안",
    "EU": "EU",
    "중남미": "중남미",
    "일본": "일본",
    "인도": "인도",
    "중동": "중동",
    "CIS": "CIS"
}


# ============================================================
#  1. 텍스트 정제 및 PDF 메타데이터 추출 유틸리티
# ============================================================

def clean_text(text: str) -> str:
    """
    추출된 PDF 텍스트의 특수문자, 불필요한 개행, 페이지 번호 등을 정제합니다.
    PostgreSQL text/jsonb 저장 시 오류를 유발하는 null byte (\x00) 및 PUA 영역 문자를 제거합니다.
    """
    if not text:
        return ""
    # 1. Null 바이트 제거 (PostgreSQL text 컬럼 필수)
    text = text.replace('\x00', '')
    # 2. 한글 HWP 생성 PDF 특유의 PUA(Private Use Area) 유니코드 제거
    text = re.sub(r'[\uf000-\uf8ff]', '', text)
    # 3. 페이지 번호 라인 제거 (예: '- 1 -', '— 12 —')
    text = re.sub(r'^\s*[-—]\s*\d+\s*[-—]\s*$', '', text, flags=re.MULTILINE)
    # 4. 동일 라인 내 다중 공백 단일화
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]
    # 5. 과도한 빈 줄 정리 (최대 2줄 개행 유지)
    cleaned = '\n'.join(lines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def extract_metadata_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    수출입동향 PDF 문서(1~4페이지) 및 파일명에서 기본 메타데이터를 자동 추출합니다.
    - doc_title: 문서 제목 (예: "2025년 6월 수출입 동향", "2025년 연간 및 12월 수출입 동향")
    - publisher: 발행처 (기본값: "산업통상자원부")
    - period: 대상 기간 (예: "2025-06-01", "2025-12-01")
    - report_date: 보도/배포 일시 (예: "2025-07-01 11:00:00")
    """
    file_basename = os.path.basename(pdf_path)
    meta = {
        "doc_title": "",
        "publisher": "산업통상자원부",
        "period": None,
        "report_date": None,
        "source_file": file_basename
    }

    p1_text = ""
    if HAS_PYMUPDF:
        try:
            doc = pymupdf.open(pdf_path)
            if len(doc) > 0:
                p1_text = doc[0].get_text()
            for p_idx in range(min(5, len(doc))):
                if "산업통상자원부" in doc[p_idx].get_text() or "산업통상부" in doc[p_idx].get_text():
                    meta["publisher"] = "산업통상자원부"
                    break
            doc.close()
        except Exception:
            pass
    elif HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(pdf_path)
            if len(reader.pages) > 0:
                p1_text = reader.pages[0].extract_text()
        except Exception:
            pass

    p1_cleaned = clean_text(p1_text)

    # 1. 대상 기간 (Period) 및 제목 (Doc Title) 추출
    if "연간 및 12월" in p1_cleaned or "연간 및 12월" in file_basename or "25년_연간_및_12월" in file_basename:
        meta["period"] = "2025-12-01"
        meta["doc_title"] = "2025년 연간 및 12월 수출입 동향"
    else:
        period_match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월', p1_cleaned)
        if not period_match:
            period_match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월', file_basename)
        if not period_match:
            period_match = re.search(r'(\d{2})년\s*(\d{1,2})월', file_basename)
            if period_match:
                year = 2000 + int(period_match.group(1))
                month = int(period_match.group(2))
                meta["period"] = f"{year:04d}-{month:02d}-01"
                meta["doc_title"] = f"{year}년 {month}월 수출입 동향"

        if period_match and not meta["period"]:
            year = int(period_match.group(1))
            if year < 100:
                year += 2000
            month = int(period_match.group(2))
            meta["period"] = f"{year:04d}-{month:02d}-01"
            meta["doc_title"] = f"{year}년 {month}월 수출입 동향"

    if not meta["period"]:
        meta["period"] = "2025-01-01"
        meta["doc_title"] = os.path.splitext(file_basename)[0][:100]

    # 2. 보도시점/배포일자 (Report Date) 추출
    dt_match = re.search(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.[^0-9\n]*(\d{1,2}):(\d{2})', p1_cleaned)
    if dt_match:
        ry, rm, rd, rh, rmin = dt_match.groups()
        meta["report_date"] = f"{int(ry):04d}-{int(rm):02d}-{int(rd):02d} {int(rh):02d}:{rmin}:00"
    else:
        d_match = re.search(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.', p1_cleaned)
        if d_match:
            ry, rm, rd = d_match.groups()
            meta["report_date"] = f"{int(ry):04d}-{int(rm):02d}-{int(rd):02d} 11:00:00"
        else:
            fn_m = re.search(r'^(\d{2})(\d{2})(\d{2})_', file_basename)
            if fn_m:
                fy, fm, fd = fn_m.groups()
                meta["report_date"] = f"20{fy}-{fm}-{fd} 11:00:00"
            elif meta["period"]:
                p_date = datetime.strptime(meta["period"], "%Y-%m-%d")
                rep_year = p_date.year if p_date.month < 12 else p_date.year + 1
                rep_month = p_date.month + 1 if p_date.month < 12 else 1
                meta["report_date"] = f"{rep_year:04d}-{rep_month:02d}-01 11:00:00"

    return meta


# ============================================================
#  2. PDF 지능형 골든 청킹 (Golden Semantic Chunking)
# ============================================================

def chunk_trade_trend_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    수출입동향 PDF 문서를 trade_trend_chunks.json 골든 스탠다드 규격에 맞춰 파싱하고 청킹합니다.
    - 1~4p (보도자료 요약): 표지 총괄, 【수출】, 【품목】, 품목군별(IT/모빌리티/석유화학/소재기계/소비재), 지역별 요약, 수입/수지 요약, 장관 평가 및 정책방향, 문서 안내
    - 중반부: 15~20대 주력 품목별 상세 (item 태그 부여), 9대 주요 지역별 상세 (region 태그 부여)
    - 후반부: 수출입 통계표 및 참고 1~4 자료 (table / narrative 태그 부여)
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    pages_raw: List[Tuple[int, str]] = []
    if HAS_PYMUPDF:
        doc = pymupdf.open(pdf_path)
        for page_idx, page in enumerate(doc, 1):
            pages_raw.append((page_idx, page.get_text()))
        doc.close()
    elif HAS_PYPDF:
        reader = pypdf.PdfReader(pdf_path)
        for page_idx, page in enumerate(reader.pages, 1):
            pages_raw.append((page_idx, page.extract_text() or ""))
    else:
        raise ImportError("pymupdf 또는 pypdf 패키지가 필요합니다. (pip install pymupdf pypdf)")

    file_basename = os.path.basename(pdf_path)
    meta = extract_metadata_from_pdf(pdf_path)
    doc_title = meta.get("doc_title") or "수출입 동향"
    period_str = meta.get("period") or "2025-01-01"
    report_date_str = meta.get("report_date") or f"{period_str} 11:00:00"

    raw_chunks: List[Dict[str, Any]] = []

    # ── 1. 보도자료 요약 페이지 파싱 (1~4p) ──
    summary_limit = min(5, len(pages_raw) + 1)
    for page_idx in range(1, summary_limit):
        p_txt = clean_text(pages_raw[page_idx - 1][1])
        if not p_txt:
            continue

        if page_idx == 1:
            # 1) 표지 > 총괄
            cover_lines = []
            for line in p_txt.split('\n'):
                if '【총괄】' in line or '【수출】' in line:
                    break
                cover_lines.append(line)
            cover_body = '\n'.join(cover_lines).strip()
            if cover_body:
                raw_chunks.append({
                    "text": f"[{doc_title} - 총괄]\n{cover_body}",
                    "section": "표지 > 총괄",
                    "content_type": "narrative",
                    "page": 1
                })

            # 2) 【수출】 or 【총괄】
            if '【총괄】' in p_txt or '【수출】' in p_txt:
                start_m = '【총괄】' if '【총괄】' in p_txt else '【수출】'
                exp_sub = p_txt[p_txt.index(start_m):]
                stop_idx = len(exp_sub)
                for marker in ['【품목】', '【품목별', '【지역】', '【수입】']:
                    if marker in exp_sub:
                        stop_idx = min(stop_idx, exp_sub.index(marker))
                exp_txt = exp_sub[:stop_idx].strip()
                raw_chunks.append({
                    "text": f"[수출] {exp_txt.replace('【총괄】', '').replace('【수출】', '').strip()}",
                    "section": "Ⅰ.수출동향 > 총괄",
                    "content_type": "narrative",
                    "page": 1
                })

            # 3) 【품목】 개요
            for p_tag in ['【품목】', '【품목별 수출】', '【품목별']:
                if p_tag in p_txt:
                    item_sub = p_txt[p_txt.index(p_tag):]
                    stop_idx = len(item_sub)
                    for marker in ['【지역】', '【수입】', '(IT)', '【']:
                        if marker in item_sub[4:]:
                            stop_idx = min(stop_idx, item_sub.index(marker, 4))
                    item_txt = item_sub[:stop_idx].strip()
                    raw_chunks.append({
                        "text": f"[품목] {item_txt.replace(p_tag, '').strip()}",
                        "section": "Ⅰ.수출동향 > 품목별 > 개요",
                        "content_type": "narrative",
                        "page": 1
                    })
                    break

        # 품목군별 서술 (IT, 모빌리티, 석유·화학, 소재·기계, 소비재)
        summary_categories = [
            ('(IT)', 'Ⅰ.수출동향 > 품목별 > IT 품목', '반도체·컴퓨터·무선통신기기·디스플레이'),
            ('(모빌리티)', 'Ⅰ.수출동향 > 품목별 > 모빌리티 (자동차/선박)', '자동차·선박'),
            ('(석유·화학제품)', 'Ⅰ.수출동향 > 품목별 > 석유·화학제품', '석유제품·석유화학'),
            ('(석유·화학)', 'Ⅰ.수출동향 > 품목별 > 석유·화학제품', '석유제품·석유화학'),
            ('(소재·기계)', 'Ⅰ.수출동향 > 품목별 > 소재·기계 (철강/일반기계/전기기기)', '철강·일반기계·전기기기'),
            ('(소비재)', 'Ⅰ.수출동향 > 품목별 > 소비재 (바이오헬스/화장품/농수산식품/생활용품)', '바이오헬스·화장품·농수산식품·생활용품')
        ]
        for cat_tag, cat_sec, cat_item in summary_categories:
            if cat_tag in p_txt:
                sub_txt = p_txt[p_txt.index(cat_tag):]
                stop_idx = len(sub_txt)
                for next_tag, _, _ in summary_categories:
                    if next_tag != cat_tag and next_tag in sub_txt:
                        stop_idx = min(stop_idx, sub_txt.index(next_tag))
                for next_marker in ['【지역】', '【수입】', '【수지】', '【평가']:
                    if next_marker in sub_txt:
                        stop_idx = min(stop_idx, sub_txt.index(next_marker))
                cat_body = sub_txt[:stop_idx].strip()
                if len(cat_body) > 30 and not any(c['section'] == cat_sec for c in raw_chunks if c['page'] == page_idx):
                    raw_chunks.append({
                        "text": cat_body,
                        "section": cat_sec,
                        "content_type": "narrative",
                        "page": page_idx,
                        "item": cat_item
                    })

        # 지역별 요약 (중국, 미국, 아세안·EU, 중동, 일본·인도·중남미·CIS)
        if '【지역】' in p_txt or '대(對)중국' in p_txt or '대중국' in p_txt:
            region_entries = [
                (['대(對)중국', '대중국'], 'Ⅰ.수출동향 > 지역별 > 중국', '중국'),
                (['대미국', '대(對)미국'], 'Ⅰ.수출동향 > 지역별 > 미국', '미국'),
                (['대아세안', '대(對)아세안', '대EU', '대(對)EU'], 'Ⅰ.수출동향 > 지역별 > 아세안·EU', '아세안·EU'),
                (['대중동', '대(對)중동'], 'Ⅰ.수출동향 > 지역별 > 중동', '중동'),
                (['(일본', '(인도', '(중남미', '(CIS'], 'Ⅰ.수출동향 > 지역별 > 일본·인도·중남미·CIS', '일본·인도·중남미·CIS')
            ]
            for keywords, reg_sec, reg_tag in region_entries:
                for kw in keywords:
                    if kw in p_txt:
                        start_idx = p_txt.index(kw)
                        sub_reg = p_txt[start_idx:]
                        stop_idx = len(sub_reg)
                        for next_kws, _, _ in region_entries:
                            for nkw in next_kws:
                                if nkw not in keywords and nkw in sub_reg:
                                    stop_idx = min(stop_idx, sub_reg.index(nkw))
                        for nmarker in ['【수입】', '【수지】', '【평가']:
                            if nmarker in sub_reg:
                                stop_idx = min(stop_idx, sub_reg.index(nmarker))
                        reg_body = sub_reg[:stop_idx].strip()
                        if len(reg_body) > 30 and not any(c['section'] == reg_sec for c in raw_chunks if c['page'] == page_idx):
                            raw_chunks.append({
                                "text": reg_body,
                                "section": reg_sec,
                                "content_type": "narrative",
                                "page": page_idx,
                                "region": reg_tag
                            })
                        break

        # 수입 요약 (2~4p)
        if '【수입】' in p_txt and page_idx in [2, 3, 4]:
            imp_sub = p_txt[p_txt.index('【수입】'):]
            stop_idx = len(imp_sub)
            if '【수지】' in imp_sub:
                stop_idx = imp_sub.index('【수지】')
            imp_txt = imp_sub[:stop_idx].replace('【수입】', '').strip()
            if len(imp_txt) > 20 and not any(c['section'] == 'Ⅱ.수입동향 > 총괄' for c in raw_chunks):
                raw_chunks.append({
                    "text": f"[수입] {imp_txt}",
                    "section": "Ⅱ.수입동향 > 총괄",
                    "content_type": "narrative",
                    "page": page_idx
                })

        # 무역수지 요약 (2~4p)
        if '【수지】' in p_txt and page_idx in [2, 3, 4]:
            bal_sub = p_txt[p_txt.index('【수지】'):]
            stop_idx = len(bal_sub)
            if '【평가' in bal_sub:
                stop_idx = bal_sub.index('【평가')
            bal_txt = bal_sub[:stop_idx].replace('【수지】', '').strip()
            if len(bal_txt) > 20 and not any(c['section'] == 'Ⅲ.무역수지동향 > 총괄' for c in raw_chunks):
                raw_chunks.append({
                    "text": f"[무역수지] {bal_txt}",
                    "section": "Ⅲ.무역수지동향 > 총괄",
                    "content_type": "narrative",
                    "page": page_idx
                })

        # 평가 및 정책방향
        if any(w in p_txt for w in ['【평가 및 정책방향】', '산업통상자원부 장관은', '산업통상부 장관은']):
            idx = p_txt.find('【평가 및 정책방향】')
            if idx == -1:
                idx = p_txt.find('산업통상')
            eval_txt = p_txt[idx:]
            if '담당 부서' in eval_txt:
                eval_txt = eval_txt[:eval_txt.index('담당 부서')].strip()
            if len(eval_txt) > 50 and not any(c['section'] == '평가 및 정책방향' for c in raw_chunks):
                raw_chunks.append({
                    "text": eval_txt.replace('【평가 및 정책방향】', '').strip(),
                    "section": "평가 및 정책방향",
                    "content_type": "narrative",
                    "page": page_idx
                })

        # 문서 안내 및 담당부서
        if any(w in p_txt for w in ['관세청 통관자료', '담당 부서']):
            idx = p_txt.find('관세청 통관자료')
            if idx == -1:
                idx = p_txt.find('담당 부서')
            guide_txt = p_txt[idx:].strip()
            if len(guide_txt) > 30 and not any(c['section'] == '문서 안내 및 담당부서' for c in raw_chunks):
                raw_chunks.append({
                    "text": guide_txt,
                    "section": "문서 안내 및 담당부서",
                    "content_type": "metadata_note",
                    "page": page_idx
                })

    # ── 2. 개요 및 상세 품목별/지역별 동향 및 통계표 (4p 이후) ──
    for page_idx in range(4, len(pages_raw) + 1):
        p_txt = clean_text(pages_raw[page_idx - 1][1])
        if not p_txt:
            continue

        # 본문 개요표 (수출입 개요)
        if '수출입 개요' in p_txt and page_idx in [4, 5, 6]:
            if any(h in p_txt for h in ['□ (수입)', '□(수입)', '□ (무역수지)', '□(무역수지)']):
                raw_chunks.append({
                    "text": p_txt,
                    "section": "Ⅰ.수출동향 > 수입 및 무역수지 개요",
                    "content_type": "narrative",
                    "page": page_idx
                })

        # 품목별(□) / 지역별(□) 상세 블록
        if '□ (' in p_txt or '□(' in p_txt:
            blocks = re.split(r'(?=\n?□\s*\()', p_txt)
            for blk in blocks:
                blk = blk.strip()
                if not blk or len(blk) < 20:
                    continue

                m_block = re.match(r'^□\s*\(([^:)]+)(?::|\))', blk)
                if not m_block:
                    continue
                name_raw = m_block.group(1).strip()

                # 품목 매칭
                item_matched = None
                for k, item_name in ITEM_MAP.items():
                    if k in name_raw:
                        item_matched = item_name
                        break
                if item_matched:
                    raw_chunks.append({
                        "text": blk,
                        "section": f"품목·지역별 상세 수출 동향 > 품목별 > {item_matched}",
                        "content_type": "narrative",
                        "page": page_idx,
                        "item": item_matched
                    })
                    continue

                # 지역 매칭
                reg_matched = None
                for r, reg_name in REGION_MAP.items():
                    if r in name_raw:
                        reg_matched = reg_name
                        break
                if reg_matched:
                    raw_chunks.append({
                        "text": blk,
                        "section": f"품목·지역별 상세 수출 동향 > 지역별 > {reg_matched}",
                        "content_type": "narrative",
                        "page": page_idx,
                        "region": reg_matched
                    })
                    continue

        # 주요 통계표 (수출추이, 수입추이, 원자재동향, 국가별 무역수지)
        if any(h in p_txt for h in ['가. 수출추이', '가. 수입추이', '나. 주요 원자재 동향', '다. 지역별 수입 추이', '주요 국가별 무역수지', '월별 수입실적', '월별 무역수지']):
            title_m = re.search(r'([가-하]\.\s*[^\n]+|주요\s*[^\n]+무역수지[^\n]*|월별\s*수입실적[^\n]*|월별\s*무역수지[^\n]*)', p_txt)
            sec_title = title_m.group(1).strip() if title_m else f"페이지 {page_idx} 통계표"
            raw_chunks.append({
                "text": p_txt,
                "section": f"수출입 통계 및 추이 > {sec_title}",
                "content_type": "table",
                "page": page_idx
            })

        # 참고자료 1~4
        for ref_num in [1, 2, 3, 4]:
            if f'참고 {ref_num}' in p_txt or f'참고{ref_num}' in p_txt:
                ref_sec_name = {
                    1: "참고1 > 월별 수출입 추이 (전년비교)",
                    2: "참고2 > 연도별 수출입 실적 통계",
                    3: "참고3 > 세부 품목 예시",
                    4: "참고4 > 통관기준 실적 분석"
                }.get(ref_num, f"참고{ref_num}")
                raw_chunks.append({
                    "text": p_txt,
                    "section": ref_sec_name,
                    "content_type": "table" if ref_num in [1, 2, 3] else "narrative",
                    "page": page_idx
                })
                break

    # ── 3. 최종 청크 리스트 및 메타데이터 구축 ──
    final_chunks: List[Dict[str, Any]] = []
    for idx, c in enumerate(raw_chunks, 1):
        chunk_id = f"chunk_{idx:03d}"
        extra_meta = {
            "doc_title": doc_title,
            "publisher": meta.get("publisher", "산업통상자원부"),
            "report_date": str(report_date_str)[:10],
            "period": str(period_str)[:7],
            "source_file": file_basename,
            "chunk_id": chunk_id,
            "section": c["section"],
            "content_type": c["content_type"],
            "page": int(c["page"])
        }
        if "item" in c:
            extra_meta["item"] = c["item"]
        if "region" in c:
            extra_meta["region"] = c["region"]

        final_chunks.append({
            "id": chunk_id,
            "text": c["text"],
            "section": c["section"],
            "contest_type": c["content_type"],
            "page": int(c["page"]),
            "extra_meta": extra_meta
        })

    return final_chunks


# ============================================================
#  3. DB 적재 함수 (PDF 및 JSON 공통 지원)
# ============================================================

def _normalize_period(raw_period: Any) -> str:
    """기간 문자열을 'YYYY-MM-01' 형식으로 정규화합니다."""
    if not raw_period:
        return date.today().strftime("%Y-%m-01")
    p_str = str(raw_period).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', p_str):
        return p_str
    if re.match(r'^\d{4}-\d{2}$', p_str):
        return f"{p_str}-01"
    if re.match(r'^\d{6}$', p_str):
        return f"{p_str[:4]}-{p_str[4:6]}-01"
    return f"{date.today().year:04d}-{date.today().month:02d}-01"


def _normalize_report_date(raw_date: Any, period_str: str) -> str:
    """보고서 일자 문자열을 'YYYY-MM-DD HH:MM:SS' 형식으로 정규화합니다."""
    if not raw_date:
        return f"{period_str} 11:00:00"
    d_str = str(raw_date).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', d_str):
        return d_str[:19]
    if re.match(r'^\d{4}-\d{2}-\d{2}$', d_str):
        return f"{d_str} 11:00:00"
    return f"{period_str} 11:00:00"


def save_trade_trend_json_to_db(
    json_input: Union[str, List[Dict[str, Any]]],
    doc_title: Optional[str] = None,
    publisher: Optional[str] = None,
    period: Optional[str] = None,
    report_date: Optional[str] = None
) -> bool:
    """
    정제된 JSON 청크 리스트(또는 JSON 파일 경로)를 trade_trend_info 및 trade_trend_detail에 적재합니다.
    """
    raw_chunks: List[Dict[str, Any]] = []
    source_name = "JSON Data"

    if isinstance(json_input, str):
        candidate_paths = [
            os.path.abspath(json_input),
            os.path.abspath(os.path.join(src_dir, json_input)),
            os.path.abspath(os.path.join(project_root, json_input)),
            os.path.abspath(os.path.join(src_dir, os.path.basename(json_input)))
        ]
        full_json_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                full_json_path = p
                break

        if not full_json_path:
            try:
                raw_chunks = json.loads(json_input)
            except Exception:
                print(f"\n[오류] JSON 파일을 찾을 수 없습니다: '{json_input}'")
                return False
        else:
            source_name = os.path.basename(full_json_path)
            with open(full_json_path, 'r', encoding='utf-8') as f:
                raw_chunks = json.load(f)
    elif isinstance(json_input, list):
        raw_chunks = json_input
    else:
        print("[오류] 유효하지 않은 JSON 입력 형식입니다.")
        return False

    if not raw_chunks:
        print("[오류] 적재할 JSON 청크 데이터가 비어 있습니다.")
        return False

    first_meta = raw_chunks[0].get("metadata", {})
    target_title = (doc_title or first_meta.get("doc_title") or "2026년 7월 수출입 동향").strip()
    target_publisher = (publisher or first_meta.get("publisher") or "산업통상부").strip()
    target_period = _normalize_period(period or first_meta.get("period"))
    target_report_date = _normalize_report_date(report_date or first_meta.get("report_date"), target_period)

    print("\n" + "=" * 95)
    print(f"        [ 정제된 JSON 청크 데이터 DB 적재 ]")
    print("=" * 95)
    print(f"  ▶ 소스 출처     : {source_name}")
    print(f"  ▶ 문서 제목     : {target_title}")
    print(f"  ▶ 발행 기관     : {target_publisher}")
    print(f"  ▶ 대상 기간     : {target_period}")
    print(f"  ▶ 보도/배포일시 : {target_report_date}")
    print(f"  ▶ 총 청크 수     : {len(raw_chunks)}개")
    print("-" * 95)

    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return False

    db_base_config = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", "")
    }

    # 해당 문서만 중복 정리 (다른 월 데이터 보존)
    _clean_existing_trade_trend_data(db_base_config, target_title, target_period)

    # 1. 마스터 삽입
    info_rule_no = AgentUtils.get_rule_no()
    try:
        db_conn_info = DbConn(json.dumps({**db_base_config, "action": AgentConstants.INSERT}))
        info_insert_req = {
            "query_key": "INSERT_TRADE_TREND_INFO",
            "params": {
                "rule_no": info_rule_no,
                "doc_title": target_title,
                "publisher": target_publisher,
                "report_date": target_report_date,
                "period": target_period
            }
        }
        db_conn_info.create_request(json.dumps(info_insert_req))
        db_conn_info.create_response()
        print(f"  [마스터 등록 성공] trade_trend_info 저장 완료 (PK: {info_rule_no})")
    except Exception as e:
        print(f"[오류] trade_trend_info 마스터 레코드 저장 실패: {e}")
        return False

    # 2. 상세 청크 삽입
    detail_params = []
    type_counter: Dict[str, int] = {}

    for idx, item in enumerate(raw_chunks):
        d_rule_no = AgentUtils.get_rule_no()
        meta = item.get("metadata", {})
        c_text = item.get("text", "")
        c_section = meta.get("section", "총괄")[:100]
        c_type = meta.get("content_type", "narrative")
        c_page = int(meta.get("page", 1))

        type_counter[c_type] = type_counter.get(c_type, 0) + 1

        extra_meta = {
            "chunk_id": item.get("id", f"chunk_{idx+1:03d}"),
            "char_count": len(c_text),
            "page": c_page,
            "section": c_section,
            "content_type": c_type,
            "source_file": meta.get("source_file", source_name)
        }
        if "item" in meta:
            extra_meta["item"] = meta["item"]
        if "region" in meta:
            extra_meta["region"] = meta["region"]

        detail_params.append({
            "rule_no": d_rule_no,
            "trade_trend_no": info_rule_no,
            "trade_trend_text": c_text,
            "trade_trend_section": c_section,
            "contest_type": c_type,
            "page": c_page,
            "extra_meta": json.dumps(extra_meta, ensure_ascii=False)
        })

    try:
        db_conn_detail = DbConn(json.dumps({**db_base_config, "action": AgentConstants.INSERT}))
        detail_insert_req = {
            "query_key": "INSERT_TRADE_TREND_DETAIL",
            "params": detail_params
        }
        db_conn_detail.create_request(json.dumps(detail_insert_req))
        db_conn_detail.create_response()
        print(f"  [상세 청크 적재 성공] trade_trend_detail 테이블에 총 {len(detail_params)}건 적재 완료!")
    except Exception as e:
        print(f"[오류] trade_trend_detail 청크 데이터 저장 실패: {e}")
        return False

    _print_summary(target_title, info_rule_no, len(detail_params), type_counter, raw_chunks)
    return True


def save_trade_trend_pdf_to_db(
    pdf_path: str,
    doc_title: Optional[str] = None,
    publisher: Optional[str] = None,
    period: Optional[str] = None,
    report_date: Optional[str] = None
) -> bool:
    """
    수출입동향 PDF 파일을 파싱/골든 청킹하여 trade_trend_info 및 trade_trend_detail 테이블에 적재합니다.
    """
    candidate_paths = [
        os.path.abspath(pdf_path),
        os.path.abspath(os.path.join(src_dir, pdf_path)),
        os.path.abspath(os.path.join(project_root, pdf_path)),
        os.path.abspath(os.path.join(src_dir, os.path.basename(pdf_path)))
    ]
    full_pdf_path = None
    for p in candidate_paths:
        if os.path.exists(p):
            full_pdf_path = p
            break

    if not full_pdf_path:
        print(f"\n[오류] PDF 파일을 찾을 수 없습니다: '{pdf_path}'")
        return False

    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return False

    extracted_meta = extract_metadata_from_pdf(full_pdf_path)
    target_title = (doc_title or extracted_meta.get("doc_title") or "수출입 동향").strip()
    target_publisher = (publisher or extracted_meta.get("publisher") or "산업통상자원부").strip()
    target_period = _normalize_period(period or extracted_meta.get("period"))
    target_report_date = _normalize_report_date(report_date or extracted_meta.get("report_date"), target_period)

    print("\n" + "=" * 95)
    print(f"        [ 수출입동향 PDF 파싱 및 DB 적재 ]")
    print("=" * 95)
    print(f"  ▶ 파일명       : {os.path.basename(full_pdf_path)}")
    print(f"  ▶ 문서 제목     : {target_title}")
    print(f"  ▶ 발행 기관     : {target_publisher}")
    print(f"  ▶ 대상 기간     : {target_period}")
    print(f"  ▶ 보도/배포일시 : {target_report_date}")
    print("-" * 95)

    db_base_config = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", "")
    }

    # 해당 문서만 중복 정리 (다른 월 데이터 보존)
    _clean_existing_trade_trend_data(db_base_config, target_title, target_period)

    # PDF 골든 청킹 수행
    try:
        chunks = chunk_trade_trend_pdf(full_pdf_path)
        if not chunks:
            print("[오류] PDF에서 추출된 유효한 청크가 없습니다.")
            return False
        print(f"  [골든 청킹 완료] 총 {len(chunks)}개 의미 청크 생성 완료.")
    except Exception as e:
        print(f"[오류] PDF 청킹 실패: {e}")
        return False

    # 1. 마스터 삽입
    info_rule_no = AgentUtils.get_rule_no()
    try:
        db_conn_info = DbConn(json.dumps({**db_base_config, "action": AgentConstants.INSERT}))
        info_insert_req = {
            "query_key": "INSERT_TRADE_TREND_INFO",
            "params": {
                "rule_no": info_rule_no,
                "doc_title": target_title,
                "publisher": target_publisher,
                "report_date": target_report_date,
                "period": target_period
            }
        }
        db_conn_info.create_request(json.dumps(info_insert_req))
        db_conn_info.create_response()
        print(f"  [마스터 등록 성공] trade_trend_info 저장 완료 (PK: {info_rule_no})")
    except Exception as e:
        print(f"[오류] trade_trend_info 마스터 레코드 저장 실패: {e}")
        return False

    # 2. 상세 청크 삽입
    detail_params = []
    type_counter: Dict[str, int] = {}

    for c in chunks:
        d_rule_no = AgentUtils.get_rule_no()
        c_type = c.get("contest_type", "narrative")
        type_counter[c_type] = type_counter.get(c_type, 0) + 1

        detail_params.append({
            "rule_no": d_rule_no,
            "trade_trend_no": info_rule_no,
            "trade_trend_text": c.get("text", ""),
            "trade_trend_section": c.get("section", "")[:100],
            "contest_type": c_type,
            "page": int(c.get("page", 1)),
            "extra_meta": json.dumps(c.get("extra_meta", {}), ensure_ascii=False)
        })

    try:
        db_conn_detail = DbConn(json.dumps({**db_base_config, "action": AgentConstants.INSERT}))
        detail_insert_req = {
            "query_key": "INSERT_TRADE_TREND_DETAIL",
            "params": detail_params
        }
        db_conn_detail.create_request(json.dumps(detail_insert_req))
        db_conn_detail.create_response()
        print(f"  [상세 청크 적재 성공] trade_trend_detail 테이블에 총 {len(detail_params)}건 적재 완료!")
    except Exception as e:
        print(f"[오류] trade_trend_detail 청크 데이터 저장 실패: {e}")
        return False

    _print_summary(target_title, info_rule_no, len(detail_params), type_counter, chunks)
    return True


def _clean_existing_trade_trend_data(db_base_config: Dict[str, Any], target_title: str, target_period: str):
    """해당 월/문서가 이미 존재할 경우에만 해당 레코드를 삭제하여 중복을 방지하고 다른 문서는 보존합니다."""
    try:
        db_conn_all = DbConn(json.dumps({**db_base_config, "action": AgentConstants.SELECT}))
        db_conn_all.create_request(json.dumps({"query_key": "SELECT_ALL_TRADE_TREND_INFO", "params": {}}))
        all_rows = json.loads(db_conn_all.create_response())

        matched_rule_nos = []
        if all_rows and all_rows[0].get("rule_no"):
            for r in all_rows:
                r_title = str(r.get("doc_title", "")).replace(" ", "")
                c_title = target_title.replace(" ", "")
                r_period = str(r.get("period", ""))[:7]
                c_period = str(target_period)[:7]
                if r_period == c_period or r_title == c_title:
                    matched_rule_nos.append(r["rule_no"])

        for old_rule_no in matched_rule_nos:
            print(f"  [기존 데이터 정리] 기존 rule_no ({old_rule_no}) 데이터 삭제 중...")
            db_conn_del_d = DbConn(json.dumps({**db_base_config, "action": AgentConstants.DELETE}))
            db_conn_del_d.create_request(json.dumps({
                "query_key": "DELETE_TRADE_TREND_DETAIL_BY_INFO_NO",
                "params": {"trade_trend_no": old_rule_no}
            }))
            db_conn_del_d.create_response()

            db_conn_del_i = DbConn(json.dumps({**db_base_config, "action": AgentConstants.DELETE}))
            db_conn_del_i.create_request(json.dumps({
                "query_key": "DELETE_TRADE_TREND_INFO_BY_ID",
                "params": {"rule_no": old_rule_no}
            }))
            db_conn_del_i.create_response()
            print(f"  [정리 완료] 이전 버전({old_rule_no}) 데이터 정리 완료.")

    except Exception as e:
        print(f"  [경고] 기존 데이터 조회/정리 중 예외: {e}")


def _print_summary(target_title: str, info_rule_no: str, total_chunks: int, type_counter: Dict[str, int], chunks: List[Dict[str, Any]]):
    """적재 결과 요약 콘솔 테이블을 출력합니다."""
    print("\n" + "=" * 105)
    print(f"        [ 적재 결과 요약: {target_title} ]")
    print("=" * 105)
    print(f"  • 마스터 PK (trade_trend_no) : {info_rule_no}")
    print(f"  • 적재된 총 청크 수            : {total_chunks}개")
    print(f"  • 청크 유형별 현황            : ", end="")
    summary_types = [f"{k}: {v}건" for k, v in type_counter.items()]
    print(", ".join(summary_types))
    print("-" * 105)
    print(f"{'No':^4} | {'페이지':^6} | {'유형':^12} | {'섹션/분류':^40} | {'글자수':^6} | 내용 미리보기")
    print("-" * 105)

    sample_indices = [0, 1, 2, 5, 10, total_chunks - 1]
    sample_indices = sorted(list(set([i for i in sample_indices if i < len(chunks)])))

    for idx in sample_indices:
        c = chunks[idx]
        m = c.get("metadata") or c.get("extra_meta") or {}
        p = m.get("page", c.get("page", 1))
        t = m.get("content_type", c.get("contest_type", "narrative"))
        s = (m.get("section") or c.get("section") or "")[:40]
        c_text = c.get("text", "")
        char_len = len(c_text)
        preview = c_text[:40].replace("\n", " ")
        print(f"{idx+1:^4} | {p:^6} | {t:<12} | {s:<40} | {char_len:^6} | {preview}...")

    print("=" * 105 + "\n")


# ============================================================
#  4. 디렉터리 내 PDF 파일 일괄 적재 및 조회
# ============================================================

def process_directory_files(target_dir: str = "src") -> Dict[str, int]:
    """지정 디렉터리 내의 모든 PDF 파일을 탐색하여 순차 적재합니다 (기본 위치: src/)."""
    candidate_dirs = [
        os.path.abspath(target_dir),
        os.path.abspath(os.path.join(src_dir, target_dir)),
        os.path.abspath(os.path.join(project_root, target_dir)),
        src_dir
    ]
    search_dir = None
    for d in candidate_dirs:
        if os.path.isdir(d):
            search_dir = d
            break

    if not search_dir:
        search_dir = src_dir

    pdf_files = sorted(glob.glob(os.path.join(search_dir, "*.pdf")))

    if not pdf_files:
        print(f"\n[알림] '{search_dir}' 디렉터리에서 적재 대상 PDF 파일을 찾을 수 없습니다.")
        return {"total": 0, "success": 0, "fail": 0}

    print("\n" + "=" * 95)
    print(f"        [ 디렉터리({os.path.basename(search_dir)}) PDF 파일 일괄 DB 적재 ({len(pdf_files)}개 파일) ]")
    print("=" * 95)

    success_cnt = 0
    fail_cnt = 0

    for idx, f_path in enumerate(pdf_files, 1):
        print(f"\n[{idx}/{len(pdf_files)}] '{os.path.basename(f_path)}' 처리 중...")
        try:
            ok = save_trade_trend_pdf_to_db(f_path)
            if ok:
                success_cnt += 1
            else:
                fail_cnt += 1
        except Exception as e:
            print(f"[오류] {os.path.basename(f_path)} 처리 중 예외: {e}")
            fail_cnt += 1

    print("\n" + "=" * 95)
    print(f"        [ 전체 PDF 파일 일괄 적재 완료 ]")
    print(f"        - 성공: {success_cnt}건 / 실패: {fail_cnt}건 (총 {len(pdf_files)}개)")
    print("=" * 95 + "\n")

    return {"total": len(pdf_files), "success": success_cnt, "fail": fail_cnt}


def list_loaded_trade_trends():
    """DB에 적재된 수출입동향 마스터 및 청크 개수 현황을 조회하여 출력합니다."""
    config = AgentUtils.load_config("agent_key.json")
    if not isinstance(config, dict) or not config:
        print("[오류] agent_key.json 설정 정보를 로드할 수 없습니다.")
        return

    db_net = {
        "host": config.get("db_host", ""),
        "port": int(config.get("port", 5432)),
        "database": config.get("database", ""),
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "action": AgentConstants.SELECT
    }

    try:
        db_conn = DbConn(json.dumps(db_net))
        db_conn.create_request(json.dumps({"query_key": "SELECT_ALL_TRADE_TREND_INFO", "params": {}}))
        res_str = db_conn.create_response()
        rows = json.loads(res_str)

        if not rows or (len(rows) == 1 and not rows[0]):
            print("\n[알림] DB에 적재된 수출입동향 데이터가 없습니다.")
            return

        print("\n" + "=" * 95)
        print("        [ DB 적재된 수출입동향 목록 ]")
        print("=" * 95)
        print(f"{'No':^4} | {'문서 제목':^32} | {'대상 기간':^12} | {'발행 기관':^16} | {'등록일시':^20}")
        print("-" * 95)

        for idx, r in enumerate(rows, 1):
            title = str(r.get("doc_title", "-"))[:32]
            period = str(r.get("period", "-"))[:12]
            pub = str(r.get("publisher", "-"))[:16]
            created = str(r.get("create_date", "-"))[:19]
            print(f"{idx:^4} | {title:<32} | {period:^12} | {pub:<16} | {created:^20}")

        print("=" * 95 + "\n")

    except Exception as e:
        print(f"[오류] 적재 목록 조회 실패: {e}")


# ============================================================
#  5. 메인 CLI 진입점
# ============================================================

def main():
    if len(sys.argv) > 1:
        arg_path = sys.argv[1]
        if os.path.isfile(arg_path):
            if arg_path.endswith(".json"):
                save_trade_trend_json_to_db(arg_path)
                return
            elif arg_path.endswith(".pdf"):
                save_trade_trend_pdf_to_db(arg_path)
                return
        elif os.path.isdir(arg_path):
            process_directory_files(arg_path)
            return

    print("\n" + "=" * 65)
    print("        [ 수출입동향 로더 (trade_trend_loader) ]")
    print("=" * 65)
    print("  1. 개별 수출입동향 PDF 파일 DB 적재")
    print("  2. src 폴더 내 전체 PDF 파일 일괄 적재")
    print("  3. JSON 청크 파일 DB 적재 (trade_trend_chunks.json)")
    print("  4. DB 적재된 수출입동향 목록 조회")
    print("=" * 65)

    choice = input("원하는 작업 번호를 선택하세요 (1/2/3/4, 기본값 2): ").strip() or "2"

    if choice == "1":
        default_pdf = "src/2026년 1월 수출입동향_3보_최종_수정.pdf"
        f_input = input(f"\n▶ 적재할 PDF 파일 경로 (기본값: {default_pdf}): ").strip()
        target = f_input if f_input else default_pdf
        save_trade_trend_pdf_to_db(target)
    elif choice == "2":
        dir_input = input("\n▶ 대상 디렉터리 경로 (기본값: src): ").strip()
        target_dir = dir_input if dir_input else "src"
        process_directory_files(target_dir)
    elif choice == "3":
        default_json = "src/trade_trend_chunks.json"
        f_input = input(f"\n▶ 적재할 JSON 파일 경로 (기본값: {default_json}): ").strip()
        target = f_input if f_input else default_json
        save_trade_trend_json_to_db(target)
    elif choice == "4":
        list_loaded_trade_trends()
    else:
        print("\n[오류] 잘못된 선택입니다. 1, 2, 3, 4 중 하나를 입력하세요.")


if __name__ == "__main__":
    main()
