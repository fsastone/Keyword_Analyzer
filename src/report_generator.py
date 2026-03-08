import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import NumberFormatDescriptor
from .config import OUTPUT_DIR
import logging

logger = logging.getLogger("REPORTER")

class ReportGenerator:
    """針對單一 PDF 生成專業報表"""

    def __init__(self):
        self.output_dir = OUTPUT_DIR

    def generate(self, company_name, summary_df, heatmap_dict, chapter_df):
        """
        為特定的公司生成獨立報表
        
        Args:
            company_name: 公司名稱
            summary_df: 包含 Root_Concept, E/S/G Count, E/S/G % 的匯總數據
            heatmap_dict: {Root_Concept: {Page_Num: Count}} 的熱點數據
            chapter_df: 由 LLM 解析出的章節範圍 DataFrame
        """
        output_path = self.output_dir / f"{company_name}_analysis.xlsx"
        
        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # 1. Summary (包含 Root_Concept, E/S/G 統計)
                summary_df.to_excel(writer, index=False, sheet_name='Summary')
                
                # 設定百分比格式
                ws_summary = writer.sheets['Summary']
                self._apply_percent_format(ws_summary, summary_df)
                
                # 2. Report Structure (由 LLM 解析出的範圍)
                if not chapter_df.empty:
                    chapter_df.to_excel(writer, index=False, sheet_name='Report_Chapters')
                
                # 3. Hotspot Matrix
                if heatmap_dict:
                    # 將字典轉換為 DataFrame，Index 是 Main_Keyword, Columns 是 Page_Num
                    matrix_df = pd.DataFrame.from_dict(heatmap_dict, orient='index').fillna(0)
                    
                    # 確保索引包含所有在 summary_df 中出現的 Main_Keyword (排除總計行)，並保持順序
                    all_keywords = [k for k in summary_df['Main_Keyword'].tolist() if not k.startswith("【")]
                    matrix_df = matrix_df.reindex(all_keywords, fill_value=0)
                    
                    # 將欄位名稱 (頁碼) 轉換為整數並排序
                    matrix_df.columns = [int(c) for c in matrix_df.columns]
                    matrix_df = matrix_df.reindex(sorted(matrix_df.columns), axis=1)
                    
                    matrix_df.to_excel(writer, sheet_name='Hotspot_Matrix')
                    self._apply_heatmap(writer.sheets['Hotspot_Matrix'], matrix_df.shape[0]+1, matrix_df.shape[1]+1)
                
            display_path = str(output_path)
            if len(display_path) > 40:
                display_path = "..." + display_path[-37:]
            logger.info(f"報表已生成: {display_path}")
            return output_path
        except Exception as e:
            logger.error(f"報表生成失敗 ({company_name}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _apply_percent_format(self, ws, df):
        """將百分比欄位設定為 Excel 的百分比格式"""
        for col_idx, col_name in enumerate(df.columns, 1):
            if '%' in col_name:
                letter = get_column_letter(col_idx)
                for row_idx in range(2, len(df) + 2):
                    ws.cell(row=row_idx, column=col_idx).number_format = '0.00%'

    def _apply_heatmap(self, ws, max_row, max_col):
        """套用 Excel 色階格式：按列(Row)進行分析，並跳過全為 0 的列"""
        color_scale_rule = ColorScaleRule(
            start_type='num', start_value=0, start_color='FFFFFF', # 0 為白色
            mid_type='percentile', mid_value=50, mid_color='FFFF00', # 50% 為黃色
            end_type='max', end_color='FF0000' # 最大值為紅色
        )
        
        for row_idx in range(2, max_row + 1):
            # 檢查該列的值，確定最大值是否大於 0
            row_max = 0
            for col_idx in range(2, max_col + 1):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val and isinstance(val, (int, float)):
                    if val > row_max:
                        row_max = val
            
            # 如果整列最大值是 0，則不需要套用色階 (保持白色)
            if row_max == 0:
                continue
                
            first_col = get_column_letter(2)
            last_col = get_column_letter(max_col)
            addr = f"{first_col}{row_idx}:{last_col}{row_idx}"
            ws.conditional_formatting.add(addr, color_scale_rule)
