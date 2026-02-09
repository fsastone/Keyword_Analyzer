import shutil
import logging
from pathlib import Path
from .config import ARCHIVE_DIR, OCR_NEEDED_DIR

logger = logging.getLogger(__name__)

class FileManager:
    """管理檔案移動與歸檔"""

    @staticmethod
    def archive_file(file_path: Path):
        """處理成功的檔案移至歸檔區"""
        try:
            target = ARCHIVE_DIR / file_path.name
            shutil.move(str(file_path), str(target))
            logger.info(f"檔案已歸檔: {file_path.name}")
        except Exception as e:
            logger.error(f"歸檔失敗 {file_path.name}: {e}")

    @staticmethod
    def mark_as_ocr_needed(file_path: Path):
        """文字提取失敗的檔案移至 OCR 待處理區"""
        try:
            target = OCR_NEEDED_DIR / file_path.name
            shutil.move(str(file_path), str(target))
            logger.info(f"檔案已移至 OCR 待處理區: {file_path.name}")
        except Exception as e:
            logger.error(f"移動至 OCR 區失敗 {file_path.name}: {e}")

    @staticmethod
    def get_input_files(input_dir: Path):
        """獲取待處理的 PDF 檔案列表"""
        return list(input_dir.glob("*.pdf"))
