import os
import fitz  # PyMuPDF

class CVImageExtractor:
    def __init__(self, output_dir="./temp_cv_images/"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def pdf_to_images(self, pdf_path: str) -> list:
        """Renderiza cada página del archivo PDF en imágenes PNG de 300 DPI."""
        doc = fitz.open(pdf_path)
        image_paths = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            output_path = os.path.join(self.output_dir, f"page_{page_num}_{os.path.basename(pdf_path)}.png")
            pix.save(output_path)
            image_paths.append(output_path)
            
        return image_paths

    def clear_temp_images(self, image_paths: list):
        """Borra las imágenes del disco duro, respetando la directiva de depuración."""
        from config import settings
        
        if settings.DEBUG_MODE:
            print("[EXTRACTOR] Modo Depuración Activo: Conservando imágenes temporales en disco.")
            return

        for path in image_paths:
            if os.path.exists(path):
                os.remove(path)
        print("[EXTRACTOR] Limpieza de espacio en disco concluida con éxito.")