import logging
from pathlib import Path
from tqdm import tqdm
import pandas as pd
import json

from src.config import RAW_PDFS_DIR, KEYWORDS, MAX_PAGES_TO_EXTRACT
from src.text_extractor import TextExtractor
from src.llm_service import LLMService
from src.analyzer import KeywordAnalyzer
from src.file_manager import FileManager
from src.report_generator import ReportGenerator

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("=== ESG 關鍵字分析系統啟動 ===")
    
    # 初始化組件
    extractor = TextExtractor()
    llm = LLMService()
    analyzer = KeywordAnalyzer()
    file_manager = FileManager()
    reporter = ReportGenerator()
    
    # 獲取輸入檔案
    pdf_files = file_manager.get_input_files(RAW_PDFS_DIR)
    if not pdf_files:
        logger.warning(f"在 {RAW_PDFS_DIR} 中找不到 PDF 檔案。")
        return

    all_results = []

    for pdf_path in tqdm(pdf_files, desc="處理 PDF"):
        logger.info(f"正在處理: {pdf_path.name}")
        
        # 1. 提取文字 (可透過 config 限制頁數以節省 token)
        full_text = extractor.extract_text(pdf_path, max_pages=MAX_PAGES_TO_EXTRACT)
        if not extractor.validate_text(full_text):
            logger.warning(f"檔案 {pdf_path.name} 文字內容過少，移至 OCR 待處理區。")
            file_manager.mark_as_ocr_needed(pdf_path)
            continue
            
        # 2. 利用 LLM 進行章節識別 (模擬分段)
        # 這裡我們取前 5 頁來識別目錄
        preview_text = full_text[:5000] # 粗略取前段
        chapters = llm.segment_chapters(preview_text)
        if chapters:
            logger.info(f"識別到章節: {json.dumps(chapters, ensure_ascii=False)}")
        
        # 3. 關鍵字統計 (依照類別)
        detailed_counts = analyzer.count_keywords(full_text)
        
        # 彙整結果
        record = {
            'company': pdf_path.stem,
            'total_pages': len(full_text) // 2000, # 粗略估計
        }
        
        # 展開所有類別的關鍵字計數
        for category, kws in detailed_counts.items():
            for kw, count in kws.items():
                record[kw] = count
        
        all_results.append(record)
        
        # 4. 檔案歸檔
        file_manager.archive_file(pdf_path)

    # 5. 生成報表
    if all_results:
        df = pd.DataFrame(all_results)
        df = analyzer.calculate_metrics(df)
        reporter.generate(df)
        logger.info("分析任務全部完成。")
    else:
        logger.info("沒有可分析的數據。")

if __name__ == "__main__":
    main()
