import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule
from .config import OUTPUT_DIR, REPORT_FILENAME
import logging

logger = logging.getLogger(__name__)

class ReportGenerator:
    """生成包含熱點矩陣與證據索引的 Excel 報表"""

    def __init__(self):
        self.output_path = OUTPUT_DIR / REPORT_FILENAME

    def generate(self, summary_df, heatmap_df, evidence_df):
        """
        summary_df: 總結統計
        heatmap_df: 頁碼/關鍵字矩陣
        evidence_df: 上下文證據
        """
        try:
            with pd.ExcelWriter(self.output_path, engine='openpyxl') as writer:
                # 1. 總結統計頁
                summary_df.to_excel(writer, index=False, sheet_name='Summary')
                
                # 2. 熱點矩陣頁
                if not heatmap_df.empty:
                    # 這裡建立樞紐表：列為關鍵字，欄為頁碼
                    matrix = heatmap_df.pivot_table(
                        index='Keyword', 
                        columns='Page', 
                        values='Count', 
                        fill_value=0
                    )
                    matrix.to_excel(writer, sheet_name='Hotspot_Matrix')
                    
                    ws = writer.sheets['Hotspot_Matrix']
                    # 修正：呼叫類別方法 self._apply_heatmap
                    self._apply_heatmap(ws, matrix.shape[0] + 1, matrix.shape[1] + 1)
                
                # 3. 證據索引頁 (確保這部分執行)
                if not evidence_df.empty:
                    evidence_df.to_excel(writer, index=False, sheet_name='Context_Evidence')
                    logger.info(f"成功寫入證據索引表，共 {len(evidence_df)} 筆資料")
                else:
                    logger.warning("證據索引表為空，未寫入。")
            
            logger.info(f"進階熱點報表已成功生成: {self.output_path}")
        except Exception as e:
            logger.error(f"報表生成過程中發生錯誤: {e}", exc_info=True)

    def _apply_heatmap(self, ws, max_row, max_col):
        """套用 Excel 色階格式：按列(Row)進行分析，觀察單一關鍵字在各頁面的分佈"""
        color_scale_rule = ColorScaleRule(
            start_type='min', start_color='FFFFFF',
            mid_type='percentile', mid_value=50, mid_color='FFFF00',
            end_type='max', end_color='FF0000'
        )
        
        # 從第 2 列開始(資料列)，到最後一列
        for row_idx in range(2, max_row + 1):
            # 第一欄是關鍵字名稱，所以從第二欄 (B) 開始套用色階
            first_col_letter = get_column_letter(2)
            last_col_letter = get_column_letter(max_col)
            addr = f"{first_col_letter}{row_idx}:{last_col_letter}{row_idx}"
            ws.conditional_formatting.add(addr, color_scale_rule)