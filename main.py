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

import logging
from pathlib import Path
from tqdm import tqdm
import pandas as pd
import json
import sys

# 自定義 Handler 讓 Logging 與 Tqdm 兼容
class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

# 設定 Logging 格式：標籤固定 10 字元，等級固定 7 字元
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)-10.10s] [%(levelname)-7.7s] %(message)s',
    handlers=[TqdmLoggingHandler()]
)
logger = logging.getLogger("MAIN")

# 壓制第三方庫 (包含不同的 SDK 命名空間)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

def main():
    logger.info("=== ESG 關鍵字智慧分析系統啟動 ===")
    
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
    all_chapter_data = []

    # 設定進度條 ncols=60 (較短且固定)，動態調整長度可能導致閃爍
    for pdf_path in tqdm(pdf_files, desc="分析中", ncols=70):
        pages_data = extractor.extract_text_by_pages(pdf_path, max_pages=MAX_PAGES_TO_EXTRACT)
        if not extractor.validate_text(pages_data):
            file_manager.mark_as_ocr_needed(pdf_path)
            continue
            
        # 1. LLM 章節分析 (獲取該報告特有的導覽目錄)
        preview_text = "".join([p['content'] for p in pages_data[:5]])
        chapters, usage_info = llm.segment_chapters(preview_text)
        
        if chapters:
            # 將 JSON 轉為長格式 DataFrame
            for pillar, titles in chapters.items():
                for title in titles:
                    all_chapter_data.append({
                        'Company': pdf_path.stem,
                        'ESG_Pillar': pillar,
                        'Chapter_Title': title
                    })

        # 2. 熱點與位置分析
        hotspot_df, evidence_df = analyzer.analyze_with_positions(pages_data)
        
        if not hotspot_df.empty:
            total_counts = hotspot_df.groupby('Keyword')['Count'].sum().to_dict()
            record = {'company': pdf_path.stem, 'total_pages': len(pages_data)}
            record.update(total_counts)
            summary_records.append(record)
            
            hotspot_df['Company'] = pdf_path.stem
            evidence_df['Company'] = pdf_path.stem
            all_hotspot_data.append(hotspot_df)
            all_evidence_data.append(evidence_df)
        
        file_manager.archive_file(pdf_path)

    # 3. 生成報表
    if summary_records:
        df_summary = pd.DataFrame(summary_records)
        df_summary = analyzer.calculate_metrics(df_summary)
        
        df_hotspot = pd.concat(all_hotspot_data) if all_hotspot_data else pd.DataFrame()
        df_evidence = pd.concat(all_evidence_data) if all_evidence_data else pd.DataFrame()
        df_chapters = pd.DataFrame(all_chapter_data) if all_chapter_data else pd.DataFrame()
        
        reporter.generate(df_summary, df_hotspot, df_evidence, df_chapters)
        
        usage = llm.get_usage_report()
        logger.info(f"=== Token 使用報告: 總計 {usage['Total Tokens']} ===")
        logger.info("分析完成！")

if __name__ == "__main__":
    main()
