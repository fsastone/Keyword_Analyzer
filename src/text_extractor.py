import pypdf
import logging
import re
from pathlib import Path
from typing import List, Dict
from collections import Counter

logger = logging.getLogger("EXTRACTOR")

class TextExtractor:
    """處理 PDF 文字提取、驗證與雜訊過濾"""
    
    @staticmethod
    def extract_text_by_pages(pdf_path: Path, max_pages: int = None, remove_boilerplate: bool = True) -> tuple[List[Dict], int]:
        """
        回傳 (pages_data, total_pages_in_pdf)
        pages_data: List[Dict], 包含頁碼與內容
        total_pages_in_pdf: PDF 實際總頁數
        """
        raw_pages_data = []
        total_pages = 0
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            total_pages = len(reader.pages)
            limit = max_pages if max_pages else total_pages
            
            for i in range(limit):
                page = reader.pages[i]
                text = page.extract_text()
                if text:
                    raw_pages_data.append({
                        'page_num': i + 1,
                        'content': text
                    })
            
            if not raw_pages_data:
                return [], total_pages

            if remove_boilerplate:
                # 執行樣板文字過濾 (Boilerplate Removal)
                return TextExtractor._remove_boilerplate(raw_pages_data), total_pages
            else:
                return raw_pages_data, total_pages

        except Exception as e:
            logger.error(f"提取 PDF 文字時發生錯誤 {pdf_path.name}: {e}")
            return [], total_pages

    @staticmethod
    def get_logical_to_physical_mapping(pages_data: List[Dict]) -> Dict[int, int]:
        """
        建立邏輯頁碼到物理頁碼的映射。
        採用信心權重演算法：優先考慮行首/行尾數字，並尋找最長的合理單調鏈。
        """
        high_confidence = [] # [(logical, physical)]
        low_confidence = []  # [(logical, physical)]
        
        # 更強大的匹配：
        # 匹配行首: ^(Page|P\.|第)?\s*(\d{1,3})\b
        # 匹配行尾: \b(\d{1,3})\s*(?:-|/|Page|頁)?\s*$
        start_pattern = re.compile(r"^\s*(?:Page|P\.|第)?\s*(\d{1,3})\b", re.IGNORECASE)
        end_pattern = re.compile(r"\b(\d{1,3})\s*(?:-|/|Page|頁)?\s*$", re.IGNORECASE)
        # 頁碼有時被符號包圍，如 - 25 -
        enclosed_pattern = re.compile(r"(?:^|\s)-\s*(\d{1,3})\s*-(?:\s|$)", re.IGNORECASE)
        # 廣泛匹配：尋找行中孤立或伴隨分隔符的數字
        broad_pattern = re.compile(r"(?:^|[\s|/\|])(\d{1,3})(?:[\s|/\|]|$)", re.IGNORECASE)
        
        for page in pages_data:
            p_idx = page['page_num']
            lines = [l.strip() for l in page['content'].split('\n') if l.strip()]
            
            # 檢查前 5 行與後 5 行 (增加搜尋深度)
            candidate_indices = list(range(min(5, len(lines)))) + list(range(max(0, len(lines)-5), len(lines)))
            candidate_indices = sorted(list(set(candidate_indices)))
            
            found_on_this_page = False
            for idx in candidate_indices:
                line = lines[idx]
                
                # 1. 高信心：精確匹配行首或行尾
                m_enc = enclosed_pattern.search(line)
                m_start = start_pattern.search(line)
                m_end = end_pattern.search(line)
                
                if m_enc:
                    high_confidence.append((int(m_enc.group(1)), p_idx))
                    found_on_this_page = True
                elif m_start:
                    high_confidence.append((int(m_start.group(1)), p_idx))
                    found_on_this_page = True
                elif m_end:
                    high_confidence.append((int(m_end.group(1)), p_idx))
                    found_on_this_page = True
                
                if found_on_this_page: break
            
            # 2. 低信心：搜尋整頁可能的數字
            if not found_on_this_page:
                for line in lines:
                    found = broad_pattern.findall(line)
                    for n in found:
                        low_confidence.append((int(n), p_idx))

        # 篩選候選點：優先使用高信心點
        candidates = sorted(list(set(high_confidence)))
        if len(candidates) < 10: # 提高門檻，如果高信心點不足，才引入低信心點
            # 過濾低信心點：只保留看起來像頁碼的 (小於總頁數的 1.5 倍)
            max_expected = len(pages_data) * 1.5
            filtered_low = [c for c in low_confidence if c[0] <= max_expected]
            candidates = sorted(list(set(high_confidence + filtered_low)))

        if not candidates:
            return {1: 1}

        # 尋找最佳單調路徑
        best_path = []
        # 增加起始點嘗試次數
        for start_idx in range(min(50, len(candidates))):
            current_path = [candidates[start_idx]]
            for i in range(start_idx + 1, len(candidates)):
                l_val, p_val = candidates[i]
                last_l, last_p = current_path[-1]
                
                if l_val > last_l and p_val >= last_p:
                    diff_l = l_val - last_l
                    diff_p = p_val - last_p
                    
                    # 合理性檢查：斜率在合理範圍 (0.3 ~ 3.0)
                    if 0.3 <= (diff_p / diff_l if diff_l > 0 else 1) <= 3.0:
                        current_path.append((l_val, p_val))
                    elif diff_p == 0 and diff_l > 0: # 2-up 情況
                        current_path.append((l_val, p_val))
            
            if len(current_path) > len(best_path):
                best_path = current_path

        # 轉換為最終 mapping
        mapping = {l: p for l, p in best_path}
        
        if mapping:
            min_l = min(mapping.keys())
            if min_l > 1:
                # 簡單推算第一頁
                mapping[1] = max(1, mapping[min_l] - (min_l - 1))
        else:
            mapping = {1: 1}

        return mapping

    @staticmethod
    def _remove_boilerplate(pages_data: List[Dict], threshold: float = 0.6) -> List[Dict]:
        """
        識別並移除在 60% 以上頁面中重複出現的行 (例如頁首頁尾)
        """
        total_pages = len(pages_data)
        if total_pages < 3: # 頁數太少不執行過濾，避免誤刪
            return pages_data

        # 1. 統計每一行在多少個「不同頁面」出現過
        line_doc_counts = Counter()
        for page in pages_data:
            # 將內容拆分為行，並進行標準化處理 (去除前後空白)
            unique_lines_in_page = set(line.strip() for line in page['content'].split('\n') if line.strip())
            for line in unique_lines_in_page:
                line_doc_counts[line] += 1

        # 2. 識別樣板文字 (出現頻次 > threshold)
        boilerplate_lines = {
            line for line, count in line_doc_counts.items() 
            if count > total_pages * threshold
        }

        if boilerplate_lines:
            logger.info(f"偵測到 {len(boilerplate_lines)} 行樣板文字並已自動剔除")
            # 偵錯用：可以印出前幾個被刪除的樣板文字
            sample_bp = list(boilerplate_lines)[:3]
            logger.info(f"樣板範例: {sample_bp}")

        # 3. 重組頁面內容
        cleaned_data = []
        for page in pages_data:
            lines = page['content'].split('\n')
            # 僅保留不在 boilerplate_lines 中的行
            cleaned_lines = [line for line in lines if line.strip() not in boilerplate_lines]
            cleaned_data.append({
                'page_num': page['page_num'],
                'content': '\n'.join(cleaned_lines)
            })
            
        return cleaned_data

    @staticmethod
    def validate_text(pages_data: List[Dict]) -> bool:
        """驗證提取的總字數"""
        total_text = "".join([p['content'] for p in pages_data])
        return len(total_text.strip()) >= 500
