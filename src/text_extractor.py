import pypdf
import logging
from pathlib import Path
from typing import List, Dict
from collections import Counter

logger = logging.getLogger("EXTRACTOR")

class TextExtractor:
    """處理 PDF 文字提取、驗證與雜訊過濾"""
    
    @staticmethod
    def extract_text_by_pages(pdf_path: Path, max_pages: int = None) -> List[Dict]:
        """
        回傳 List[Dict]，並自動過濾頁首頁尾等重複雜訊
        """
        raw_pages_data = []
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
                return []

            # 執行樣板文字過濾 (Boilerplate Removal)
            cleaned_pages_data = TextExtractor._remove_boilerplate(raw_pages_data)
            return cleaned_pages_data

        except Exception as e:
            logger.error(f"提取 PDF 文字時發生錯誤 {pdf_path.name}: {e}")
            return []

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