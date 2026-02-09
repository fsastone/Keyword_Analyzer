import os
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

# 確保目錄存在
for path in [RAW_PDFS_DIR, ARCHIVE_DIR, OCR_NEEDED_DIR, OUTPUT_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Gemini 設定
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = "gemini-2.5-flash"  # 使用使用者要求的版本

# 關鍵字定義
KEYWORDS = {
    "Environmental": [
        "碳中和", "淨零", "減碳", "再生能源", "綠能", "節能", "水資源", "廢棄物", "循環經濟", "氣候變遷"
    ],
    "Social": [
        "員工福利", "人權", "性別平等", "職業安全", "社區參與", "人才培訓", "多元包容", "隱私保護"
    ],
    "Governance": [
        "董事會", "商業道德", "誠信經營", "反貪腐", "風險管理", "供應鏈管理", "股東權益", "法規遵循"
    ],
    "Tech/Innovation": [
        "人工智慧", "AI", "機器學習", "數位轉型", "物聯網", "IoT", "自動化", "大數據", "雲端運算"
    ]
}

# 報表設定
REPORT_FILENAME = "esg_tech_keyword_analysis.xlsx"

# 測試/開發設定
# 設定提取的頁數限制，None 代表提取全部頁面
# 若要節省 token 與時間，可設定為小數字 (例如 5)
MAX_PAGES_TO_EXTRACT = 5
