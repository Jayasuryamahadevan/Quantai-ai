import io
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import pandas as pd
from pathlib import Path
import docx
import os
import shutil

# Respect an explicit path, then PATH, then the common Windows installation.
pytesseract.pytesseract.tesseract_cmd = (
    os.getenv("TESSERACT_CMD")
    or shutil.which("tesseract")
    or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text = ""
    for page_num in range(len(doc)):
        page = doc[page_num]
        text += str(page.get_text()) + "\n"
        # Extract images and OCR
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image = Image.open(io.BytesIO(image_bytes))
                ocr_text = pytesseract.image_to_string(image)
                if ocr_text.strip():
                    text += f"\n[Image OCR Text]: {ocr_text}\n"
            except Exception as e:
                pass
    return text

def extract_text_from_docx(file_path: str) -> str:
    doc = docx.Document(file_path)
    text = "\n".join([p.text for p in doc.paragraphs])
    # Extract images from docx
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            try:
                img_data = rel.target_part.blob
                image = Image.open(io.BytesIO(img_data))
                ocr_text = pytesseract.image_to_string(image)
                if ocr_text.strip():
                    text += f"\n[Image OCR Text]: {ocr_text}\n"
            except Exception as e:
                pass
    return text

def extract_text_from_txt(file_path: str) -> str:
    content = Path(file_path).read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")

def extract_text(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    elif ext == ".txt":
        return extract_text_from_txt(file_path)
    elif ext in [".csv", ".xlsx"]:
        df = pd.read_csv(file_path) if ext == ".csv" else pd.read_excel(file_path)
        return df.to_string(index=False)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
