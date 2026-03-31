"""
pdf_ingestor.py
===============
PDF 文字擷取服務。

支援兩種模式：
1. 數位 PDF（有文字層）：pymupdf（fitz）直接提取，速度快、品質高
2. 掃描 PDF（純圖片）：PaddleOCR（中文 OCR，離線）

選擇策略（自動偵測）：
- 嘗試 pymupdf 提取，若每頁平均文字 < 50 字 → 判定為掃描件，切換 OCR
- 也可強制指定 engine="digital" | "ocr" | "auto"

安裝依賴：
    pip install pymupdf          # 數位 PDF（必要）
    pip install paddlepaddle     # OCR CPU 版
    pip install paddleocr        # OCR 模型
    # 或輕量替代：
    pip install pymupdf easyocr  # EasyOCR 備選

GitHub 推薦組件：
- pymupdf:    https://github.com/pymupdf/PyMuPDF         (★ 數位 PDF 首選)
- paddleocr:  https://github.com/PaddlePaddle/PaddleOCR  (★ 中文掃描首選)
- easyocr:    https://github.com/JaidedAI/EasyOCR        (備選，安裝更簡單)
- surya:      https://github.com/VikParuchuri/surya       (現代 OCR，需 GPU)
"""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path
from typing import Literal, Optional

from .scene_splitter import normalize_text

logger = logging.getLogger(__name__)

EngineType = Literal["auto", "digital", "ocr"]

# 每頁平均少於此字數 → 判定為掃描件
_MIN_CHARS_PER_PAGE_DIGITAL = 50


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def pdf_to_text(
    source: "str | Path | bytes",
    engine: EngineType = "auto",
    ocr_lang: str = "ch",          # PaddleOCR 語言：ch / en / chinese_cht
    page_range: Optional[tuple[int, int]] = None,  # (start_page, end_page)，1-indexed，None = 全部
    dpi: int = 200,                 # 轉圖時的解析度（OCR 模式）
) -> str:
    """
    PDF → 純文字。

    Args:
        source:     檔案路徑、Path 物件，或 bytes（已讀入的 PDF 內容）
        engine:     "auto" 自動偵測 | "digital" 強制數位 | "ocr" 強制 OCR
        ocr_lang:   OCR 語言代碼（PaddleOCR 格式）
        page_range: (start, end) 1-indexed，None 代表全部頁
        dpi:        OCR 頁面渲染解析度（建議 150–300）

    Returns:
        正規化後的純文字字串
    """
    pdf_bytes = _load_bytes(source)

    if engine == "auto":
        engine = _detect_engine(pdf_bytes, page_range)
        logger.info("pdf_to_text: auto-detected engine = %s", engine)

    if engine == "digital":
        text = _extract_digital(pdf_bytes, page_range)
    else:
        text = _extract_ocr(pdf_bytes, page_range, lang=ocr_lang, dpi=dpi)

    return normalize_text(text)


# ---------------------------------------------------------------------------
# 內部：載入
# ---------------------------------------------------------------------------


def _load_bytes(source: "str | Path | bytes") -> bytes:
    if isinstance(source, bytes):
        return source
    path = Path(source)
    return path.read_bytes()


# ---------------------------------------------------------------------------
# 內部：自動偵測
# ---------------------------------------------------------------------------


def _detect_engine(pdf_bytes: bytes, page_range) -> EngineType:
    """嘗試 pymupdf 提取第一頁，判斷是否為數位 PDF。"""
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        start, end = _resolve_range(len(doc), page_range)
        sample_pages = list(range(start, min(start + 3, end)))
        total_chars = sum(
            len(doc[p].get_text("text").strip()) for p in sample_pages
        )
        avg = total_chars / max(len(sample_pages), 1)
        doc.close()
        return "digital" if avg >= _MIN_CHARS_PER_PAGE_DIGITAL else "ocr"
    except Exception as e:
        logger.warning("_detect_engine failed: %s → fallback to digital", e)
        return "digital"


# ---------------------------------------------------------------------------
# 內部：數位 PDF 提取（pymupdf）
# ---------------------------------------------------------------------------


def _extract_digital(pdf_bytes: bytes, page_range) -> str:
    """
    使用 pymupdf 提取數位 PDF 文字。
    保留原始換行結構（適合小說段落偵測）。
    """
    try:
        import fitz
    except ImportError as e:
        raise ImportError(
            "pymupdf 未安裝。請執行：pip install pymupdf"
        ) from e

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    start, end = _resolve_range(len(doc), page_range)
    pages_text: list[str] = []

    for page_num in range(start, end):
        page = doc[page_num]
        # "text" 模式：保留換行，適合連續段落
        page_text = page.get_text("text")
        if page_text.strip():
            pages_text.append(page_text)

    doc.close()
    return "\n".join(pages_text)


# ---------------------------------------------------------------------------
# 內部：OCR 提取（PaddleOCR）
# ---------------------------------------------------------------------------


def _extract_ocr(
    pdf_bytes: bytes,
    page_range,
    lang: str = "ch",
    dpi: int = 200,
) -> str:
    """
    使用 PaddleOCR 對掃描 PDF 進行 OCR。
    先用 pymupdf 將頁面渲染成圖片，再送 OCR。
    """
    # 嘗試 PaddleOCR，失敗則 fallback EasyOCR
    try:
        return _ocr_with_paddle(pdf_bytes, page_range, lang=lang, dpi=dpi)
    except ImportError:
        logger.warning("PaddleOCR 未安裝，嘗試 EasyOCR...")
    try:
        return _ocr_with_easyocr(pdf_bytes, page_range, lang=lang, dpi=dpi)
    except ImportError:
        raise ImportError(
            "OCR 模式需要安裝 PaddleOCR 或 EasyOCR：\n"
            "  pip install paddlepaddle paddleocr\n"
            "  或：pip install easyocr"
        )


def _ocr_with_paddle(pdf_bytes: bytes, page_range, lang: str, dpi: int) -> str:
    """PaddleOCR 實作（中文掃描件首選）。"""
    from paddleocr import PaddleOCR  # type: ignore
    import fitz
    import numpy as np

    # 初始化（use_angle_cls=True 處理旋轉文字）
    ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    start, end = _resolve_range(len(doc), page_range)
    results: list[str] = []

    for page_num in range(start, end):
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_array = np.frombuffer(pix.tobytes("png"), dtype=np.uint8)

        # OCR 執行
        result = ocr.ocr(img_array, cls=True)
        if result and result[0]:
            lines = [line[1][0] for line in result[0] if line and line[1]]
            results.append("\n".join(lines))

    doc.close()
    return "\n\n".join(results)


def _ocr_with_easyocr(pdf_bytes: bytes, page_range, lang: str, dpi: int) -> str:
    """EasyOCR 備選實作（安裝更簡單）。"""
    import easyocr  # type: ignore
    import fitz

    # EasyOCR 語言代碼轉換
    _lang_map = {"ch": ["ch_sim", "en"], "chinese_cht": ["ch_tra", "en"], "en": ["en"]}
    easyocr_langs = _lang_map.get(lang, ["ch_sim", "en"])

    reader = easyocr.Reader(easyocr_langs, gpu=False)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    start, end = _resolve_range(len(doc), page_range)
    results: list[str] = []

    for page_num in range(start, end):
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        ocr_result = reader.readtext(img_bytes, detail=0, paragraph=True)
        results.append("\n".join(ocr_result))

    doc.close()
    return "\n\n".join(results)


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------


def _resolve_range(
    total_pages: int,
    page_range: Optional[tuple[int, int]],
) -> tuple[int, int]:
    """將 1-indexed page_range 轉為 0-indexed (start, end) Python range。"""
    if page_range is None:
        return 0, total_pages
    start_1, end_1 = page_range
    start = max(0, start_1 - 1)
    end = min(total_pages, end_1)
    return start, end


def check_dependencies() -> dict[str, bool]:
    """回傳已安裝的 PDF 相依套件狀態。"""
    status: dict[str, bool] = {}
    for pkg, name in [("fitz", "pymupdf"), ("paddleocr", "paddleocr"), ("easyocr", "easyocr")]:
        try:
            __import__(pkg)
            status[name] = True
        except ImportError:
            status[name] = False
    return status
