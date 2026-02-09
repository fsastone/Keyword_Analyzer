# ESG Intelligence Analyzer: 企業永續報告自動化語義分析系統

> **核心價值**：利用大型語言模型 (LLM) 與自動化文本挖掘技術，將數百頁的 ESG 永續報告書轉化為可視化的決策矩陣與熱點地圖，大幅提升投資分析師與研究員的審閱效率。

---

## 📌 問題陳述 (Problem Statement)
隨著全球對 ESG (環境、社會、公司治理) 的重視，分析師面臨以下痛點：
- **資訊過載**：單份 ESG 報告動輒超過 100 頁，人工審閱耗時且成本高昂。
- **語境識別困難**：傳統關鍵字搜尋無法區分「口號式提及」與「實質性投入」。
- **導覽障礙**：不同企業的報告架構差異極大，難以快速定位特定 ESG 議題的討論分佈。

## 🏗️ 系統架構 (Solution Architecture)
本系統採用「混合式 (Hybrid) 分析管線」設計，兼顧 LLM 的語義理解能力與傳統程式的精確統計：

```mermaid
graph TD
    A[PDF 原始報告] --> B[Text Extractor]
    B --> C{文字層校驗}
    C -- 有效 --> D[Gemini 2.5 Flash]
<<<<<<< HEAD
    C -- 損壞 --> E["OCR 待處理區<br>(OCR 功能未新增)"]
=======
    C -- 損壞 --> E[OCR 待處理區 (OCR 功能未新增)]
>>>>>>> 672ab427d95ded9a52376464e006bae9b70fc38c
    
    subgraph "AI 語義層"
        D --> F[章節結構識別]
    end
    
    subgraph "數據計算層"
        B --> G[Regex 關鍵字匹配]
        G --> H[計量指標運算]
        H --> I[熱點分布計算]
    end
    
    F --> J[Report Generator]
    I --> J
    G --> J[證據索引擷取]
    
    J --> K[Excel 專業多維度報表]
```

**數據流說明：**
1. **Intelligence (LLM)**: 調用 Gemini 2.5 Flash 僅分析前幾頁，識別該企業特有的 ESG 章節標題，產出導航地圖。
2. **Analytics (Local)**: 透過本地 Regex 進行全文本關鍵字掃描，計算 **Ln(Freq+1)** 與 **Skewness (偏態)**。
3. **Heatmap & Evidence**: 產出橫向色階熱點圖，並自動擷取關鍵字前後 40 字的上下文作為查核證據。

## 🛠️ 技術棧 (Tech Stack)
- **AI/LLM**: Google Gemini API (Gemini-2.5-Flash)
- **數據處理**: Pandas, NumPy
- **報表引擎**: Openpyxl (Advanced Conditional Formatting)
- **PDF 引擎**: PyPDF
- **環境管理**: Python-dotenv, Logging

## 🌟 核心功能 (Key Features)
- **三維熱點對照系統**：
    - **`Report_Chapters`**: LLM 識別的報告導航圖，對應企業自定義章節。
    - **`Hotspot_Matrix`**: 橫向色階分析，觀察單一關鍵字在不同頁碼的分布強度。
    - **`Context_Evidence`**: 自動標註 ESG 分類，並提供語境證據供人工快速核實。
- **高效 Token 管線**：僅在需要語義導航時使用 LLM，統計任務由本地處理，最小化 Token 支出。
- **計量分析指標**：包含頻次、對數平滑值與分布偏態，量化企業報告的側重點。
- **自動化歸檔系統**：處理完畢後自動移至 `archive/`，失敗檔案則引導至 `ocr_needed/`。

## 🚀 快速上手 (Setup & Usage)

### 1. 環境設定
```bash
pip install -r requirements.txt
```

### 2. 配置 .env
```text
GOOGLE_API_KEY=您的_API_Key
```

### 3. 執行分析
將 PDF 放入 `raw_pdfs/` 並執行：
```bash
python main.py
```

## 📂 專案結構 (Project Structure)
```text
Keyword_Analyzer/
├── src/
│   ├── config.py           # 集中化配置 (關鍵字清單、模型參數)
│   ├── text_extractor.py   # PDF 提取與驗證邏輯
│   ├── llm_service.py      # Gemini API 整合與 Token 監控
│   ├── analyzer.py         # 計量統計、上下文擷取與分類標註
│   ├── report_generator.py # 多工作表 Excel 渲染與熱點圖
│   └── file_manager.py     # 檔案生命週期管理 (歸檔/OCR)
├── main.py                 # 系統進入點與分析管線協調
└── requirements.txt        # 專案依賴清單
```

---
**Disclaimer**: 本專案僅供學術研究與投資分析參考，實際投資決策應結合更多維度之評估。