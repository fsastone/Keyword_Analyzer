import pypdf
import logging
import re
from pathlib import Path
from typing import List, Dict
from collections import Counter

logger = logging.getLogger("TXT_EX")

class TextExtractor:
    """處理 PDF 文字提取、驗證與雜訊過濾"""
    
    @staticmethod
    def extract_text_by_pages(pdf_path: Path, max_pages: int = None, remove_boilerplate: bool = True) -> tuple[List[Dict], int]:
        """
        回傳 (pages_data, total_pages)
        支援 PDF 與 TXT
        """
        if pdf_path.suffix.lower() == ".txt":
            try:
                with open(pdf_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return [{'page_num': 1, 'content': content}], 1
            except Exception as e:
                logger.error(f"讀取文字檔失敗 {pdf_path.name}: {e}")
                return [], 0

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
        優化：僅搜尋頁面最頂端與最底端，並支援羅馬數字與前綴。
        """
        high_confidence = []
        
        # 嚴格匹配模式
        # 匹配行首/行尾的孤立數字，或是帶有 Page/P./- 標籤的數字
        # 優化：行首數字必須是唯一的或是帶有標籤，避免抓到章節編號 (如 01, 02)
        patterns = [
            re.compile(r"^\s*(?:Page|P\.|第)\s*(\d{1,3})\b", re.IGNORECASE),
            re.compile(r"^\s*(\d{1,3})\s*$", re.IGNORECASE), # 只有數字的行
            re.compile(r"\b(\d{1,3})\s*(?:-|/|Page|頁)?\s*$", re.IGNORECASE),
            re.compile(r"^\s*-\s*(\d{1,3})\s*-\s*$", re.IGNORECASE)
        ]
        
        # 羅馬數字匹配 (i, ii, iii...)
        roman_pattern = re.compile(r"^\s*(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})\s*$", re.IGNORECASE)

        for page in pages_data:
            p_idx = page['page_num']
            lines = [l.strip() for l in page['content'].split('\n') if l.strip()]
            if not lines: continue
            
            # 僅檢查前 3 行與後 3 行，避免誤抓內文數字
            check_lines = lines[:3] + lines[-3:]
            
            for line in check_lines:
                # 優先檢查純羅馬數字
                if roman_pattern.match(line):
                    continue

                for pat in patterns:
                    m = pat.search(line)
                    if m:
                        val = int(m.group(1))
                        # 只有當數字在合理範圍內才列入考慮 (例如 < 總頁數 + 50)
                        if val < len(pages_data) + 50:
                            high_confidence.append((val, p_idx))
                            break

        candidates = sorted(list(set(high_confidence)))
        if not candidates:
            return {1: 1}

        # 尋找最佳單調路徑 (RANSAC 簡化版)
        best_path = []
        for start_idx in range(min(10, len(candidates))):
            current_path = [candidates[start_idx]]
            for i in range(start_idx + 1, len(candidates)):
                l_val, p_val = candidates[i]
                last_l, last_p = current_path[-1]
                
                # 斜率必須接近 1 (允許 0.8 ~ 1.2)
                if l_val > last_l and p_val > last_p:
                    slope = (p_val - last_p) / (l_val - last_l)
                    if 0.8 <= slope <= 1.2:
                        current_path.append((l_val, p_val))
            
            if len(current_path) > len(best_path):
                best_path = current_path

        # 如果找出的路徑太短 (例如只有 1 個點)，且該點與物理頁碼差異過大，則視為雜訊
        if len(best_path) == 1:
            l_val, p_val = best_path[0]
            if abs(l_val - p_val) > 10:
                logger.warning(f"捨棄可疑的單一映射點: L={l_val} -> P={p_val}")
                return {1: 1}

        mapping = {l: p for l, p in best_path}
        return mapping if mapping else {1: 1}

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
            logger.info(f"偵測到 {len(boilerplate_lines)} 行樣板文字已剔除")
            # 偵錯用：印出縮短後的樣板文字
            sample_list = []
            for line in list(boilerplate_lines)[:2]:
                truncated = (line[:25] + '..') if len(line) > 25 else line
                sample_list.append(truncated)
            logger.info(f"樣板範例: {sample_list}")

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
    def validate_text(pages_data: List[Dict], min_avg_chars: int = 50) -> bool:
        """
        驗證提取的總字數與平均字數。
        如果平均每頁字數太少，通常代表該頁是圖片或提取失敗。
        """
        if not pages_data:
            return False
            
        total_text = "".join([p['content'] for p in pages_data])
        total_len = len(total_text.strip())
        avg_len = total_len / len(pages_data)
        
        # 總字數太少，或平均每頁字數太少，則視為無效提取
        if total_len < 500 or avg_len < min_avg_chars:
            logger.warning(f"文字提取驗證未通過: 總字數 {total_len}, 平均每頁 {avg_len:.1f} 字。")
            return False
            
        return True
