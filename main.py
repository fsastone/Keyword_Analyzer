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

# 設定 Logging 格式與 Tqdm 兼容
class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

logging.basicConfig(
    level=logging.INFO,
    format='[%(name)-10.10s] [%(levelname)-7.7s] %(message)s',
    handlers=[TqdmLoggingHandler()]
)
logger = logging.getLogger("MAIN")

# 壓制第三方庫
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

    for pdf_path in tqdm(pdf_files, desc="分析中", ncols=70):
        company_name = pdf_path.stem
        
        # 1. 提取文字
        pages_data = extractor.extract_text_by_pages(pdf_path, max_pages=MAX_PAGES_TO_EXTRACT)
        if not extractor.validate_text(pages_data):
            file_manager.mark_as_ocr_needed(pdf_path)
            continue
            
        # 2. LLM 章節分析
        preview_text = "".join([p['content'] for p in pages_data[:5]])
        chapters, usage_info = llm.segment_chapters(preview_text)
        
        current_chapters = []
        if chapters:
            for pillar, titles in chapters.items():
                for title in titles:
                    current_chapters.append({
                        'Company': company_name,
                        'ESG_Pillar': pillar,
                        'Chapter_Title': title
                    })
            if usage_info:
                logger.info(f"LLM 消耗: {usage_info['total']} tokens (P: {usage_info['prompt']}, C: {usage_info['completion']})")

        # 3. 熱點與位置分析
        hotspot_df, evidence_df = analyzer.analyze_with_positions(pages_data)
        
        # 4. 針對「當前檔案」生成獨立報表
        if not hotspot_df.empty or True: # 即使沒有命中也生成報表
            # 獲取所有定義的關鍵字列表
            all_keywords = [kw for sublist in analyzer.keywords.values() for kw in sublist]
            
            # 初始化所有關鍵字為 0
            summary_record = {kw: 0 for kw in all_keywords}
            summary_record.update({'company': company_name, 'total_pages': len(pages_data)})
            
            # 更新實際命中的次數
            if not hotspot_df.empty:
                total_counts = hotspot_df.groupby('Keyword')['Count'].sum().to_dict()
                summary_record.update(total_counts)
            
            df_summary = pd.DataFrame([summary_record])
            
            # 確保欄位順序一致 (公司資訊在前，關鍵字在後)
            cols = ['company', 'total_pages'] + all_keywords
            df_summary = df_summary[cols]
            
            df_summary = analyzer.calculate_metrics(df_summary)
            df_chapters = pd.DataFrame(current_chapters)
            
            # 產出該 PDF 的專屬報表
            reporter.generate(company_name, df_summary, hotspot_df, evidence_df, df_chapters)
        
        # 5. 檔案歸檔
        file_manager.archive_file(pdf_path)

    # 最終總結報告
    usage = llm.get_usage_report()
    logger.info(f"=== 任務完成 | 累計消耗 Token: {usage['Total Tokens']} ===")

if __name__ == "__main__":
    main()