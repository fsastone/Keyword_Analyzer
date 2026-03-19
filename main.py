import logging
from pathlib import Path
from tqdm import tqdm
import pandas as pd
import json
import re

from src.config import RAW_PDFS_DIR, MAX_PAGES_TO_EXTRACT, ESG_CHAPTER_OVERRIDES
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

def extract_company_and_year(filename: str):
    """
    從檔名中提取公司名稱與年份。
    預期格式如: 2023-MediaTek-ESG-Report_Chinese.pdf 或 MediaTek_2022.pdf
    """
    # 嘗試匹配 4 位數字作為年份
    year_match = re.search(r'(19|20)\d{2}', filename)
    year = year_match.group(0) if year_match else "Unknown"
    
    # 移除年份、副檔名以及常見關鍵字來獲取公司名稱
    clean_name = filename
    if year_match:
        clean_name = clean_name.replace(year, "")
    
    clean_name = re.sub(r'\.pdf$', '', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'[-_]ESG[-_]Report.*', '', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'[-_]ESG.*', '', clean_name, flags=re.IGNORECASE)
    clean_name = clean_name.strip('-_ ')
    
    # 如果處理後為空，回傳原始檔名（不含副檔名）
    if not clean_name:
        clean_name = Path(filename).stem
        
    return clean_name, year

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

    # 用於儲存所有公司的所有年度數據
    company_data_store = {} # {company_id: [df1, df2, ...]}

    for pdf_path in tqdm(pdf_files, desc="分析中", ncols=70):
        full_stem = pdf_path.stem
        company_id, report_year = extract_company_and_year(pdf_path.name)
        logger.info(f"正在處理: {company_id} ({report_year})")
        
        # 1. 提取文字
        pages_data, total_pdf_pages = extractor.extract_text_by_pages(pdf_path, max_pages=MAX_PAGES_TO_EXTRACT, remove_boilerplate=True)
        
        if not pages_data or not extractor.validate_text(pages_data):
            logger.warning(f"檔案 {pdf_path.name} 文字提取失敗或過短，轉入 OCR 待處理區。")
            file_manager.mark_as_ocr_needed(pdf_path)
            continue
            
        # 2. ESG 章節解析
        if full_stem in ESG_CHAPTER_OVERRIDES:
            logger.info(f"偵測到 {full_stem} 的手動章節設定，跳過 LLM 解析。")
            esg_ranges = ESG_CHAPTER_OVERRIDES[full_stem]
        else:
            raw_pages_for_toc, _ = extractor.extract_text_by_pages(pdf_path, max_pages=25, remove_boilerplate=False)
            toc_text_for_llm = "\n".join([p['content'] for p in raw_pages_for_toc])
            
            if not toc_text_for_llm.strip():
                logger.error(f"公司 {company_id} 的 TOC 提取內容為空！")
                esg_ranges = {"analysis": "Empty TOC", "E": [], "S": [], "G": []}
            else:
                raw_pages_for_mapping, _ = extractor.extract_text_by_pages(pdf_path, remove_boilerplate=False)
                mapping = extractor.get_logical_to_physical_mapping(raw_pages_for_mapping)
                esg_ranges = llm.parse_esg_toc(toc_text_for_llm, total_pdf_pages, mapping)
            
        # 整理章節範圍用於報表
        chapter_data = []
        for section in ["E", "S", "G"]:
            ranges = esg_ranges.get(section, [])
            for r in ranges:
                chapter_data.append({
                    'Section': section,
                    'Start_Page': r.get('start', 0),
                    'End_Page': r.get('end', 0)
                })
        df_chapters = pd.DataFrame(chapter_data)

        # 3. 執行概念字典分析
        summary_data, heatmap_dict = analyzer.analyze_document(pages_data, esg_ranges)
        df_summary = pd.DataFrame(summary_data)
        
        # 插入識別資訊
        df_summary.insert(0, 'Year', report_year)
        df_summary.insert(0, 'Company', company_id)
        df_summary.insert(2, 'Total_Pages', len(pages_data))

        # 4. 計算統計指標
        df_summary = analyzer.calculate_metrics(df_summary)
        
        # 5. 產出該 PDF 的專屬報表
        reporter.generate(full_stem, df_summary, heatmap_dict, df_chapters)
        
        # 6. 儲存數據以供後續彙總
        if company_id not in company_data_store:
            company_data_store[company_id] = []
        company_data_store[company_id].append(df_summary)
        
        # 7. 檔案歸檔
        file_manager.archive_file(pdf_path)

    # 執行公司層級的彙總報表
    for company_id, dfs in company_data_store.items():
        if len(dfs) >= 1: # 即使只有一個年度也產生彙總，方便比較
            logger.info(f"正在為 {company_id} 生成跨年度彙總報表...")
            all_years_df = pd.concat(dfs, ignore_index=True)
            reporter.generate_company_summary(company_id, all_years_df)

    usage = llm.get_usage_report()
    logger.info(f"=== 任務完成 | 累計消耗 Token: {usage['Total Tokens']} ===")

if __name__ == "__main__":
    main()
