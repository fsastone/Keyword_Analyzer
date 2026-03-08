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
        
        # 匹配行首或行尾的 1-3 位數字
        start_pattern = re.compile(r"^\s*(\d{1,3})\b")
        end_pattern = re.compile(r"\b(\d{1,3})\s*$")
        isolated_pattern = re.compile(r"\b(\d{1,3})\b")
        
        for page in pages_data:
            p_idx = page['page_num']
            lines = [l.strip() for l in page['content'].split('\n') if l.strip()]
            
            for line in lines:
                m_start = start_pattern.search(line)
                m_end = end_pattern.search(line)
                
                if m_start:
                    high_confidence.append((int(m_start.group(1)), p_idx))
                elif m_end:
                    high_confidence.append((int(m_end.group(1)), p_idx))
                else:
                    found = isolated_pattern.findall(line)
                    for n in found:
                        low_confidence.append((int(n), p_idx))

        # 篩選候選點：優先使用高信心點
        candidates = sorted(list(set(high_confidence)))
        if len(candidates) < 5: # 如果高信心點太少，補充低信心點
            candidates = sorted(list(set(high_confidence + low_confidence)))

        if not candidates:
            return {}

        # 尋找最佳單調路徑 (RANSAC 簡化版)
        # 嘗試從不同起點建立路徑，並保留最長且最合理的一條
        best_path = []
        
        # 為了效能，我們只從前幾個候選點開始嘗試
        for start_idx in range(min(10, len(candidates))):
            current_path = [candidates[start_idx]]
            for i in range(start_idx + 1, len(candidates)):
                l_val, p_val = candidates[i]
                last_l, last_p = current_path[-1]
                
                # 檢查是否單調遞增且斜率合理 (ASE 可能是 1-up)
                if l_val > last_l and p_val >= last_p:
                    # 邏輯頁碼增加與物理頁碼增加的比例應在 0.4 到 2.5 之間
                    # (涵蓋 2-up 與包含許多無頁碼插頁的情況)
                    diff_l = l_val - last_l
                    diff_p = p_val - last_p
                    if diff_p <= diff_l * 2 + 2: # 允許一定的寬容度
                        current_path.append((l_val, p_val))
            
            if len(current_path) > len(best_path):
                best_path = current_path

        # 轉換為最終 mapping
        mapping = {l: p for l, p in best_path}
        
        # 補強：確保第一個邏輯頁面有定義
        if mapping:
            min_l = min(mapping.keys())
            if min_l > 1:
                # 假設第一頁在物理第一頁或附近
                mapping[1] = 1
        else:
            # 極端情況：完全沒抓到
            mapping[1] = 1

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