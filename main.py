import logging
from pathlib import Path
from tqdm import tqdm
import pandas as pd
import json

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
        
        # 1. 提取文字 (分別提取原始文字與過濾後文字)
        pages_data, total_pdf_pages = extractor.extract_text_by_pages(pdf_path, max_pages=MAX_PAGES_TO_EXTRACT, remove_boilerplate=True)
        
        if not pages_data or not extractor.validate_text(pages_data):
            logger.warning(f"檔案 {pdf_path.name} 文字提取失敗或過短，轉入 OCR 待處理區。")
            file_manager.mark_as_ocr_needed(pdf_path)
            continue
            
        # 2. ESG 章節解析 (優先檢查手動設定)
        if company_name in ESG_CHAPTER_OVERRIDES:
            logger.info(f"偵測到 {company_name} 的手動章節設定，跳過 LLM 解析。")
            esg_ranges = ESG_CHAPTER_OVERRIDES[company_name]
        else:
            # LLM TOC 解析 (分析前 15 頁文字，暫不開啟 Boilerplate Removal 以免誤刪重要目錄)
            raw_pages_for_toc, _ = extractor.extract_text_by_pages(pdf_path, max_pages=15, remove_boilerplate=False)
            
            # Debug: 儲存 TOC 文本供檢查，包含頁碼標記
            toc_text_with_markers = ""
            for p in raw_pages_for_toc:
                toc_text_with_markers += f"\n--- Page {p['page_num']} ---\n{p['content']}\n"
            
            debug_toc_path = Path("output") / f"debug_{company_name}_toc.txt"
            with open(debug_toc_path, "w", encoding="utf-8") as f:
                f.write(toc_text_with_markers)
            
            toc_text_for_llm = "\n".join([p['content'] for p in raw_pages_for_toc])
            if not toc_text_for_llm.strip():
                logger.error(f"公司 {company_name} 的 TOC 提取內容為空！")
                esg_ranges = {"analysis": "Empty TOC", "E": [], "S": [], "G": []}
            else:
                # 建立邏輯頁碼到物理頁碼的映射 (使用原始文字以確保頁碼不被樣板過濾)
                raw_pages_for_mapping, _ = extractor.extract_text_by_pages(pdf_path, remove_boilerplate=False)
                mapping = extractor.get_logical_to_physical_mapping(raw_pages_for_mapping)
                logger.info(f"建立頁碼映射完成，共識別出 {len(mapping)} 個邏輯頁面點。")
                
                # 使用 PDF 實際總頁數 (total_pdf_pages) 與 mapping 進行解析
                esg_ranges = llm.parse_esg_toc(toc_text_for_llm, total_pdf_pages, mapping)
            
        # 整理章節範圍用於報表
        chapter_data = []
        for section in ["E", "S", "G"]:
            ranges = esg_ranges.get(section, [])
            if not ranges:
                logger.warning(f"公司 {company_name} 的 {section} 章節未識別到任何範圍。")
            
            for r in ranges:
                # 確保獲取的是整數
                try:
                    start_p = int(r.get('start', 0))
                    end_p = int(r.get('end', 0))
                except (ValueError, TypeError):
                    logger.error(f"公司 {company_name} 的 {section} 章節頁碼格式錯誤: {r}")
                    start_p, end_p = 0, 0
                
                chapter_data.append({
                    'Section': section,
                    'Start_Page': start_p,
                    'End_Page': end_p
                })
        df_chapters = pd.DataFrame(chapter_data)
        
        logger.info(f"ESG 章節範圍解析完成 (E/S/G 各有 {len(esg_ranges.get('E',[]))}/{len(esg_ranges.get('S',[]))}/{len(esg_ranges.get('G',[]))} 個區間)")

        # 3. 執行概念字典 (Synonyms Dictionary) 分析與統計
        summary_data, heatmap_dict = analyzer.analyze_document(pages_data, esg_ranges)
        df_summary = pd.DataFrame(summary_data)
        
        # 插入公司資訊
        df_summary.insert(0, 'Company', company_name)
        df_summary.insert(1, 'Total_Pages', len(pages_data))

        # 4. 計算統計指標 (Log 轉換等)
        df_summary = analyzer.calculate_metrics(df_summary)
        
        # 5. 產出該 PDF 的專屬報表
        reporter.generate(company_name, df_summary, heatmap_dict, df_chapters)
        
        # 6. 檔案歸檔
        file_manager.archive_file(pdf_path)

    # 最終總結報告
    usage = llm.get_usage_report()
    logger.info(f"=== 任務完成 | 累計消耗 Token: {usage['Total Tokens']} ===")

if __name__ == "__main__":
    main()
