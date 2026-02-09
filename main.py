import logging
from pathlib import Path
from tqdm import tqdm
import pandas as pd
import json

from src.config import RAW_PDFS_DIR, MAX_PAGES_TO_EXTRACT
from src.text_extractor import TextExtractor
from src.llm_service import LLMService
from src.analyzer import KeywordAnalyzer
from src.file_manager import FileManager
from src.report_generator import ReportGenerator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("=== ESG 關鍵字進階分析系統啟動 ===")
    
    extractor = TextExtractor()
    llm = LLMService()
    analyzer = KeywordAnalyzer()
    file_manager = FileManager()
    reporter = ReportGenerator()
    
    pdf_files = file_manager.get_input_files(RAW_PDFS_DIR)
    if not pdf_files:
        logger.warning("找不到 PDF 檔案。")
        return

    summary_records = []
    all_hotspot_data = []
    all_evidence_data = []

    for pdf_path in tqdm(pdf_files, desc="分析中"):
        # 1. 提取分頁文字
        pages_data = extractor.extract_text_by_pages(pdf_path, max_pages=MAX_PAGES_TO_EXTRACT)
        if not extractor.validate_text(pages_data):
            file_manager.mark_as_ocr_needed(pdf_path)
            continue
            
        # 2. 熱點與位置分析
        hotspot_df, evidence_df = analyzer.analyze_with_positions(pages_data)
        
        # 3. 彙整總體數據
        if not hotspot_df.empty:
            # 統計該檔案的各關鍵字總數
            total_counts = hotspot_df.groupby('Keyword')['Count'].sum().to_dict()
            record = {'company': pdf_path.stem, 'total_pages': len(pages_data)}
            record.update(total_counts)
            summary_records.append(record)
            
            # 標註公司名稱後彙整
            hotspot_df['Company'] = pdf_path.stem
            evidence_df['Company'] = pdf_path.stem
            all_hotspot_data.append(hotspot_df)
            all_evidence_data.append(evidence_df)
        
        file_manager.archive_file(pdf_path)

    # 4. 生成報表
    if summary_records:
        df_summary = pd.DataFrame(summary_records)
        df_summary = analyzer.calculate_metrics(df_summary)
        
        df_hotspot = pd.concat(all_hotspot_data) if all_hotspot_data else pd.DataFrame()
        df_evidence = pd.concat(all_evidence_data) if all_evidence_data else pd.DataFrame()
        
        reporter.generate(df_summary, df_hotspot, df_evidence)
        logger.info("分析完成！")

if __name__ == "__main__":
    main()