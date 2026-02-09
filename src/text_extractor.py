import pypdf
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

class TextExtractor:
    """處理 PDF 文字提取與驗證 (保留頁碼資訊)"""
    
    @staticmethod
    def extract_text_by_pages(pdf_path: Path, max_pages: int = None) -> List[Dict]:
        """
        回傳 List[Dict]，每個 Dict 包含 {'page_num': int, 'content': str}
        """
        pages_data = []
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            total_pages = len(reader.pages)
            limit = max_pages if max_pages else total_pages
            
            for i in range(limit):
                page = reader.pages[i]
                text = page.extract_text()
                if text:
                    pages_data.append({
                        'page_num': i + 1,
                        'content': text
                    })
                else:
                    logger.warning(f"第 {i + 1} 頁無法提取文字: {pdf_path.name}")
            
            return pages_data
        except Exception as e:
            logger.error(f"提取 PDF 文字時發生錯誤 {pdf_path.name}: {e}")
            return []

    @staticmethod
    def validate_text(pages_data: List[Dict]) -> bool:
        """驗證提取的總字數"""
        total_text = "".join([p['content'] for p in pages_data])
        return len(total_text.strip()) >= 500
