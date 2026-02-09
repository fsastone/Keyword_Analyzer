import pypdf
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class TextExtractor:
    """處理 PDF 文字提取與驗證"""
    
    @staticmethod
    def extract_text(pdf_path: Path, max_pages: int = None) -> str:
        """
        從 PDF 提取文字 (直接提取，不使用 OCR)
        :param max_pages: 限制提取的前幾頁，None 代表提取全部
        """
        full_text = []
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            pages_to_read = reader.pages
            
            # 如果有設定 max_pages，則只讀取前 N 頁
            if max_pages is not None:
                pages_to_read = reader.pages[:max_pages]
                logger.info(f"測試模式：僅提取前 {max_pages} 頁內容")

            for page_num, page in enumerate(pages_to_read):
                text = page.extract_text()
                if text:
                    full_text.append(text)
                else:
                    logger.warning(f"第 {page_num + 1} 頁無法提取文字: {pdf_path.name}")
            
            # 使用標準換行符號連接各頁文字
            return "\n".join(full_text)
        except Exception as e:
            logger.error(f"提取 PDF 文字時發生錯誤 {pdf_path.name}: {e}")
            return ""

    @staticmethod
    def validate_text(text: str) -> bool:
        """
        驗證提取的文字是否有效 (例如：字數是否過少)
        """
        if not text:
            return False
        
        # 去除空白後計算長度
        clean_text = text.strip()
        if len(clean_text) < 500:  # 假設 ESG 報告至少應有 500 字
            return False
        return True