import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule
from .config import OUTPUT_DIR, REPORT_FILENAME
import logging

logger = logging.getLogger("REPORTER")

class ReportGenerator:
    """生成包含多維度分析與章節結構的專業報表"""

    def __init__(self):
        self.output_path = OUTPUT_DIR / REPORT_FILENAME

    def generate(self, summary_df, heatmap_df, evidence_df, chapter_df):
        """
        summary_df: 總結統計
        heatmap_df: 頁碼矩陣
        evidence_df: 上下文證據 (帶分類)
        chapter_df: LLM 識別出的報告章節結構
        """
        try:
            with pd.ExcelWriter(self.output_path, engine='openpyxl') as writer:
                # 1. Summary
                summary_df.to_excel(writer, index=False, sheet_name='Summary')
                
                # 2. Report Structure (新：LLM 識別的章節)
                if not chapter_df.empty:
                    chapter_df.to_excel(writer, index=False, sheet_name='Report_Chapters')
                
                # 3. Hotspot Matrix
                if not heatmap_df.empty:
                    matrix = heatmap_df.pivot_table(
                        index='Keyword', columns='Page', values='Count', fill_value=0
                    )
                    matrix.to_excel(writer, sheet_name='Hotspot_Matrix')
                    self._apply_heatmap(writer.sheets['Hotspot_Matrix'], matrix.shape[0]+1, matrix.shape[1]+1)
                
                # 4. Context Evidence
                if not evidence_df.empty:
                    evidence_df.to_excel(writer, index=False, sheet_name='Context_Evidence')
            
            display_path = str(self.output_path)
            if len(display_path) > 40:
                display_path = "..." + display_path[-37:]
            logger.info(f"專業報表已生成: {display_path}")
        except Exception as e:
            logger.error(f"報表生成失敗: {e}")

    def _apply_heatmap(self, ws, max_row, max_col):
        color_scale_rule = ColorScaleRule(
            start_type='min', start_color='FFFFFF',
            mid_type='percentile', mid_value=50, mid_color='FFFF00',
            end_type='max', end_color='FF0000'
        )
        for row_idx in range(2, max_row + 1):
            addr = f"{get_column_letter(2)}{row_idx}:{get_column_letter(max_col)}{row_idx}"
            ws.conditional_formatting.add(addr, color_scale_rule)
