import logging
import os
import argparse
from pathlib import Path
from tqdm import tqdm
import pandas as pd
import re
import concurrent.futures
from typing import Dict, List, Any, Optional

from src.config import RAW_PDFS_DIR, MAX_PAGES_TO_EXTRACT, ESG_CHAPTER_OVERRIDES, OUTPUT_DIR
from src.text_extractor import TextExtractor
from src.llm_service import LLMService
from src.analyzer import KeywordAnalyzer
from src.file_manager import FileManager
from src.report_generator import ReportGenerator
from src.ocr_service import OCRService

# 設定 Logging 格式與 Tqdm 兼容
class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

# 在主進程與子進程中統一配置 Logging
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(name)-6s] %(message)s',
        handlers=[TqdmLoggingHandler()]
    )
    # 壓制第三方庫
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger("_MAIN_")

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

def process_single_pdf(pdf_path: Path, is_high_volume: bool = False) -> Dict[str, Any]:
    """
    單個 PDF 的處理邏輯，適合多進程調用。
    """
    if is_high_volume:
        # 在子進程中抑制不必要的日誌
        for name in ["TXT_EX", "GEMINI", "FILMGR", "ANLYZR"]:
            logging.getLogger(name).setLevel(logging.WARNING)

    # 每個進程需要獨立實例化服務
    extractor = TextExtractor()
    llm = LLMService()
    analyzer = KeywordAnalyzer()
    file_manager = FileManager()
    reporter = ReportGenerator()
    
    result = {
        "pdf_path": pdf_path,
        "success": False,
        "company_id": None,
        "report_year": None,
        "df_summary": None,
        "usage": {"Prompt Tokens": 0, "Completion Tokens": 0, "Total Tokens": 0},
        "error": None
    }

    try:
        full_stem = pdf_path.stem
        company_id, report_year = extract_company_and_year(pdf_path.name)
        result["company_id"] = company_id
        result["report_year"] = report_year
        
        # 1. 提取文字
        pages_data, total_pdf_pages = extractor.extract_text_by_pages(pdf_path, max_pages=MAX_PAGES_TO_EXTRACT, remove_boilerplate=True)
        
        if not pages_data or not extractor.validate_text(pages_data):
            file_manager.mark_as_ocr_needed(pdf_path)
            result["error"] = "Text extraction failed or too short, moved to OCR area."
            return result
            
        # 2. ESG 章節解析
        if full_stem in ESG_CHAPTER_OVERRIDES:
            esg_ranges = ESG_CHAPTER_OVERRIDES[full_stem]
        else:
            raw_pages_for_toc, _ = extractor.extract_text_by_pages(pdf_path, max_pages=25, remove_boilerplate=False)
            toc_text_for_llm = "\n".join([p['content'] for p in raw_pages_for_toc])
            
            if not toc_text_for_llm.strip():
                esg_ranges = {"analysis": "Empty TOC", "E": [], "S": [], "G": []}
            else:
                # 頁碼映射：如果原本就是全量提取且已過濾樣板，則直接複用以節省時間與日誌雜訊
                if MAX_PAGES_TO_EXTRACT is None:
                    mapping = extractor.get_logical_to_physical_mapping(pages_data)
                else:
                    raw_pages_for_mapping, _ = extractor.extract_text_by_pages(pdf_path, remove_boilerplate=True)
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
        
        # 6. 歸檔
        file_manager.archive_file(pdf_path)
        
        result["success"] = True
        result["df_summary"] = df_summary
        result["usage"] = llm.get_usage_report()
        
    except Exception as e:
        import traceback
        result["error"] = f"{str(e)}\n{traceback.format_exc()}"
        
    return result

def generate_summaries_from_existing():
    """從 output 目錄中的現有分析檔案生成公司彙總報表"""
    logger.info("正在從現有分析檔案生成彙總報表...")
    
    # 僅獲取根目錄下的檔案，不包含子目錄
    analysis_files = [f for f in OUTPUT_DIR.iterdir() if f.is_file() and f.name.endswith("_analysis.xlsx")]
    
    if not analysis_files:
        logger.warning("在 output 目錄中找不到任何分析檔案。")
        return

    company_data_store = {}
    
    for file_path in tqdm(analysis_files, desc="讀取分析檔案", ncols=80):
        try:
            # 從檔名解析公司 ID
            filename = file_path.name.replace("_analysis.xlsx", "")
            
            # 讀取 Excel 的 Summary 頁籤
            df = pd.read_excel(file_path, sheet_name='Summary')
            
            # 獲取公司 ID (優先從第一列 'Company' 獲取)
            if 'Company' in df.columns:
                cid = df['Company'].iloc[0]
            else:
                cid, _ = extract_company_and_year(filename)
                
            if cid not in company_data_store:
                company_data_store[cid] = []
            company_data_store[cid].append(df)
        except Exception as e:
            logger.error(f"讀取 {file_path.name} 失敗: {e}")

    if company_data_store:
        reporter = ReportGenerator()
        for company_id, dfs in company_data_store.items():
            logger.info(f"正在為 {company_id} 生成跨年度彙總報表...")
            all_years_df = pd.concat(dfs, ignore_index=True)
            reporter.generate_company_summary(company_id, all_years_df)
    
    logger.info("彙總報表生成完成。")

def handle_ocr_mode():
    """處理 OCR 模式：將 ocr_needed 中的 PDF 轉換為文字"""
    from src.config import OCR_NEEDED_DIR, RAW_PDFS_DIR
    logger.info("=== 啟動 OCR 處理模式 ===")
    
    ocr_srv = OCRService()
    pdf_files = [f for f in OCR_NEEDED_DIR.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
    
    if not pdf_files:
        logger.info("ocr_needed 目錄中沒有待處理的 PDF。")
        return

    for pdf_path in tqdm(pdf_files, desc="OCR 處理中", ncols=80):
        content = ocr_srv.process_pdf(pdf_path)
        if content:
            # 將結果存為 .txt 檔案回到 raw_pdfs
            txt_path = RAW_PDFS_DIR / f"{pdf_path.stem}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"OCR 完成，文字已存至: {txt_path.name}")
            # 檔案處理後，原 PDF 移至 archive (避免重複 OCR)
            archive_path = OCR_NEEDED_DIR / "archive"
            archive_path.mkdir(exist_ok=True)
            pdf_path.rename(archive_path / pdf_path.name)
        else:
            logger.error(f"OCR 處理失敗: {pdf_path.name}")

def main():
    parser = argparse.ArgumentParser(description="ESG 關鍵字智慧分析系統")
    parser.add_argument("--summary-only", "-s", action="store_true", help="僅根據 output 目錄中的現有結果生成公司彙總報表")
    parser.add_argument("--ocr", action="store_true", help="執行 OCR 處理 ocr_needed 中的檔案")
    args = parser.parse_args()

    if args.ocr:
        handle_ocr_mode()
        return

    if args.summary_only:
        generate_summaries_from_existing()
        return

    logger.info("=== ESG 關鍵字智慧分析系統 (多進程版) 啟動 ===")
    
    file_manager = FileManager()
    pdf_files = file_manager.get_input_files(RAW_PDFS_DIR)
    
    if not pdf_files:
        logger.warning("找不到 PDF 檔案。")
        return

    # 參數設定
    max_workers = 16
    total_files = len(pdf_files)
    logger.info(f"預計處理 {total_files} 個檔案，並發執行緒數: {max_workers}")

    # 決定日誌詳盡程度 (超過 5 個檔案時開啟簡潔模式)
    is_high_volume = total_files > 5
    if is_high_volume:
        logger.info("偵測到大量檔案，將開啟簡潔日誌模式。")
        # 僅保留 MAIN 與 REPORT 的 INFO 級別，其餘調高至 WARNING
        for name in ["TXT_EX", "GEMINI", "FILMGR", "ANLYZR"]:
            logging.getLogger(name).setLevel(logging.WARNING)

    # 用於儲存彙總數據
    company_data_store = {}
    total_usage = {"Prompt Tokens": 0, "Completion Tokens": 0, "Total Tokens": 0}
    
    # 追蹤處理狀態
    success_count = 0
    fail_count = 0
    failed_files = []

    # 執行多進程處理
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任務
        future_to_pdf = {executor.submit(process_single_pdf, pdf, is_high_volume): pdf for pdf in pdf_files}
        
        # 使用 tqdm 追蹤進度
        for future in tqdm(concurrent.futures.as_completed(future_to_pdf), total=total_files, desc="分析中", ncols=80):
            pdf_path = future_to_pdf[future]
            try:
                res = future.result()
                if res["success"]:
                    success_count += 1
                    # 彙總 Token 使用量
                    for key in total_usage:
                        total_usage[key] += res["usage"].get(key, 0)
                    
                    # 儲存數據以供後續彙總
                    cid = res["company_id"]
                    if cid not in company_data_store:
                        company_data_store[cid] = []
                    company_data_store[cid].append(res["df_summary"])
                    
                    if not is_high_volume:
                        logger.info(f"完成: {res['company_id']} ({res['report_year']})")
                    # 高負載模式下，tqdm 已經提供進度，我們可以選擇不輸出或僅輸出極簡資訊
                else:
                    fail_count += 1
                    failed_files.append((pdf_path.name, res["error"]))
                    logger.error(f"失敗: {pdf_path.name}")
                    if not is_high_volume:
                         logger.error(f"原因: {res['error']}")
            except Exception as e:
                fail_count += 1
                failed_files.append((pdf_path.name, str(e)))
                logger.error(f"非預期錯誤: {pdf_path.name} | {e}")

    # 執行公司層級的彙總報表
    if company_data_store:
        reporter = ReportGenerator()
        for company_id, dfs in company_data_store.items():
            if len(dfs) >= 1:
                logger.info(f"正在為 {company_id} 生成跨年度彙總報表...")
                all_years_df = pd.concat(dfs, ignore_index=True)
                reporter.generate_company_summary(company_id, all_years_df)

    # 輸出最終總結
    logger.info("="*50)
    logger.info("=== 任務執行總結 ===")
    logger.info(f"總處理檔案數: {total_files}")
    logger.info(f"成功: {success_count}")
    logger.info(f"失敗: {fail_count}")
    
    if failed_files:
        logger.error("--- 失敗檔案列表 ---")
        for filename, error in failed_files:
            # 僅顯示錯誤的第一行，避免日誌過長
            err_msg = str(error).split('\n')[0]
            logger.error(f"  - {filename}: {err_msg}")
    
    logger.info("-" * 50)
    logger.info(f"累計消耗 Prompt Tokens: {total_usage['Prompt Tokens']}")
    logger.info(f"累計消耗 Completion Tokens: {total_usage['Completion Tokens']}")
    logger.info(f"總計消耗 Tokens: {total_usage['Total Tokens']}")
    logger.info("="*50)

if __name__ == "__main__":
    main()
