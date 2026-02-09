import os
import re
import numpy as np
import pandas as pd
import pytesseract
import pypdf
from pdf2image import convert_from_path
from tqdm import tqdm
from collections import Counter

# ==========================================
# 設定區 (Configuration)
# ==========================================

# 動態取得專案根目錄
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# 設定相對路徑
POPPLER_BIN = os.path.join(PROJECT_ROOT, 'bin', 'poppler', 'Library', 'bin')
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# 檢查是否存在，防呆
if not os.path.exists(POPPLER_BIN):
    raise FileNotFoundError(f"Poppler not found at {POPPLER_BIN}")

INPUT_FOLDER = os.path.join(BASE_DIR, '..', 'raw_pdfs')
OUTPUT_FOLDER = os.path.join(BASE_DIR, '..', 'output')

# 關鍵字定義 (包含同義詞或大小寫變體可透過正規表達式處理)
# 這裡使用簡單的列表，實際專案建議轉為類似 {'AI': ['AI', '人工智慧']} 的字典結構
KEYWORDS = [
    # 核心
    "人工智慧", "AI", "機器學習", "Machine Learning", "ML", 
    "深度學習", "Deep Learning", "DL", "自然語言處理", "NLP",
    #  infra
    "資料中心", "Data Center", "雲端運算", "Cloud Computing", "邊緣運算", "Edge Computing",
    # 應用
    "物聯網", "IoT", "智慧化", "Smart", "數位轉型", "Digital Transformation",
    "大數據", "Big Data", "自動化", "Automation", "數位孿生", "Digital Twin",
    # 資安
    "資訊安全", "Cyber Security", "區塊鏈", "Blockchain"
]

# 編譯正則表達式以加速搜尋 (忽略大小寫)
KEYWORD_PATTERNS = {kw: re.compile(re.escape(kw), re.IGNORECASE) for kw in KEYWORDS}

# ==========================================
# 核心功能函數
# ==========================================


def extract_text_from_pdf(pdf_path):
    """
    [優化版] 優先使用 pypdf 直讀文字，若失敗才考慮 OCR (本專案應可完全捨棄 OCR)。
    """
    full_text = ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        # 遍歷每一頁
        for page in reader.pages:
            # extract_text() 能直接讀取數位文字層
            text = page.extract_text()
            if text:
                full_text += text + "\n"
                
        # 簡單驗證：如果抓出來的字數太少（例如整本只有 100 字），代表可能是純圖片檔
        if len(full_text) < 200: 
            print(f"[警告] {os.path.basename(pdf_path)} 文字層極少，可能需要 OCR (目前略過)")
            return "" # 或在此處切換回原本的 OCR 函式
            
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return ""
    
    return full_text

def analyze_keywords(text):
    """
    [優化版] 針對中英文採用不同的 Regex 策略，解決 "Dubai" 與 "AI新時代" 的矛盾。
    """
    stats = {}
    
    for kw in KEYWORDS:
        # 判斷關鍵字是否包含中文字 (檢查是否所有字元都在 ASCII 範圍內)
        is_english = all(ord(c) < 128 for c in kw)
        
        if is_english:
            # 英文策略：使用 \b (詞邊界) + re.ASCII
            # 效果：能抓到 "AI", "AI.", "AI "，也能抓到 "AI新" (因中文在 ASCII 模式下視為邊界)
            #       但會忽略 "Dubai", "Mail"
            pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE | re.ASCII)
        else:
            # 中文策略：不使用邊界，直接匹配子字串
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            
        matches = pattern.findall(text)
        stats[kw] = len(matches)
        
    return stats

def calculate_advanced_metrics(df_result):
    """
    進行統計轉換：Ln(Freq+1) 與 分布偏態
    """
    # 1. Ln(x+1) 轉換：避免 0 造成 log 無限大，並平滑極端值
    # 針對所有關鍵字欄位進行轉換
    for kw in KEYWORDS:
        df_result[f'ln_{kw}'] = np.log1p(df_result[kw])
    
    # 2. 計算該份報告的關鍵字分布偏態 (Skewness)
    # 這裡的邏輯是：這家公司的報告是否「過度集中」在某幾個關鍵字？
    # 我們對「每一列 (Row)」的原始頻次數據計算偏態
    kw_cols = KEYWORDS  # 原始頻次欄位
    
    # axis=1 代表對每一列(每家公司)計算
    df_result['dist_skewness'] = df_result[kw_cols].skew(axis=1)
    
    # 3. 額外統計：科技關鍵字總聲量 (Tech Buzz Volume)
    df_result['total_tech_mentions'] = df_result[kw_cols].sum(axis=1)
    
    return df_result

# ==========================================
# 主程式
# ==========================================

def main():
    print("=== 永續報告書關鍵字分析系統啟動 ===")
    
    report_data = []
    pdf_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print(f"警告：{INPUT_FOLDER} 資料夾中沒有 PDF 檔案。")
        return

    # 使用 tqdm 顯示進度條
    for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
        pdf_path = os.path.join(INPUT_FOLDER, pdf_file)
        company_name = os.path.splitext(pdf_file)[0]  # 假設檔名即公司名
        
        # 1. 提取文字 (OCR)
        raw_text = extract_text_from_pdf(pdf_path)
        
        if not raw_text:
            continue
            
        # 2. 統計關鍵字
        kw_stats = analyze_keywords(raw_text)
        
        # 3. 整合資料
        record = {'company': company_name}
        record.update(kw_stats)
        report_data.append(record)

    # 4. 轉為 DataFrame 並進行數學轉換
    if report_data:
        df = pd.DataFrame(report_data)
        
        # 進行進階統計運算
        df_final = calculate_advanced_metrics(df)
        
        # 5. 輸出報告
        output_path = os.path.join(OUTPUT_FOLDER, 'esg_tech_keyword_analysis.xlsx')
        df_final.to_excel(output_path, index=False)
        print(f"\n分析完成！報告已儲存至：{output_path}")
        print(f"包含欄位：原始頻次、Ln轉換值、偏態係數(Skewness)")
    else:
        print("沒有產生任何數據。")

if __name__ == "__main__":
    main()