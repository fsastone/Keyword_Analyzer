import os
import json
from pathlib import Path
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 專案路徑設定
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_PDFS_DIR = BASE_DIR / "raw_pdfs"
ARCHIVE_DIR = RAW_PDFS_DIR / "archive"
OCR_NEEDED_DIR = RAW_PDFS_DIR / "ocr_needed"
OUTPUT_DIR = BASE_DIR / "output"
SUMMARIES_DIR = OUTPUT_DIR / "company_summaries"

# 確保目錄存在
for path in [RAW_PDFS_DIR, ARCHIVE_DIR, OCR_NEEDED_DIR, OUTPUT_DIR, SUMMARIES_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# 關鍵字定義路徑
KEYWORD_DICT_PATH = Path(__file__).resolve().parent / "keyword_dictionary.json"

# 載入概念字典 (Taxonomy)
if KEYWORD_DICT_PATH.exists():
    with open(KEYWORD_DICT_PATH, 'r', encoding='utf-8') as f:
        KEYWORD_DICT = json.load(f)
else:
    KEYWORD_DICT = {}

# Gemini 設定
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = "gemini-3-flash-preview"  # 使用使用者要求的版本

# 報表設定
REPORT_FILENAME = "esg_tech_keyword_analysis.xlsx"

# 手動章節範圍設定 (若 LLM 識別不精確時使用)
# 格式為 { "公司名稱": { "E": {"start": 10, "end": 20}, ... } }
ESG_CHAPTER_OVERRIDES = {
    "範例公司_2023_ESG報告": {
        "E": {"start": 5, "end": 40},
        "S": {"start": 41, "end": 70},
        "G": {"start": 71, "end": 90}
    }
}

# 測試/開發設定
# 設定提取的頁數限制，None 代表提取全部頁面
# 若要節省 token 與時間，可設定為小數字 (例如 5)
MAX_PAGES_TO_EXTRACT = None