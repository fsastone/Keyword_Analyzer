import logging
from pathlib import Path
from markitdown import MarkItDown

logger = logging.getLogger("OCR_SRV")

class OCRService:
    """使用 Microsoft MarkItDown 進行 OCR 處理"""
    
    def __init__(self):
        self.md = MarkItDown()

    def process_pdf(self, pdf_path: Path) -> str:
        """將 PDF 轉換為 Markdown 文字 (含 OCR)"""
        try:
            logger.info(f"正在對 {pdf_path.name} 執行 OCR...")
            result = self.md.convert(str(pdf_path))
            return result.text_content
        except Exception as e:
            logger.error(f"OCR 處理失敗 {pdf_path.name}: {e}")
            return ""
