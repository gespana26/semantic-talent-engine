"""Módulo encargado del procesamiento gráfico, rasterización y ciclo de vida de activos de documentos temporales."""
import os

import fitz  # PyMuPDF
from PIL import Image


class CVImageExtractor:
    """Componente encargado de la rasterización y limpieza de documentos PDF."""

    def _make_multiple_of_28(self, value: int) -> int:
        """Calcula el mayor múltiplo de 28 que no excede el valor, para evitar el bug de tensores de Qwen-VL en Ollama."""
        return (value // 28) * 28

    def pdf_to_images(self, pdf_path: str) -> list:
        """Convierte las páginas del PDF a imágenes matemáticamente compatibles con Qwen2.5-VL."""
        doc = fitz.open(pdf_path)
        image_paths = []
        
        # Mantenemos el escalado base para que Qwen lea con nitidez
        zoom_matrix = fitz.Matrix(1.5, 1.5) 
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=zoom_matrix)
            
            output_path = f"temp_page_{page_num}.png"
            pix.save(output_path)
            
            # --- PARCHE DE INMUNIDAD PARA QWEN2.5-VL ---
            # Interceptamos la imagen y forzamos que sus dimensiones sean divisibles por 28
            with Image.open(output_path) as img:
                old_width, old_height = img.size
                new_width = self._make_multiple_of_28(old_width)
                new_height = self._make_multiple_of_28(old_height)
                
                # Si las dimensiones no eran cuadrículas perfectas, aplicamos el redimensionamiento
                if old_width != new_width or old_height != new_height:
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    resized_img.save(output_path)
            # -------------------------------------------
                    
            image_paths.append(output_path)
            
        return image_paths

    def clear_temp_images(self, image_paths: list):
        """Limpia los archivos gráficos temporales generados durante la inferencia."""
        for path in image_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"[LOG] No se pudo eliminar la imagen temporal {path}: {e}")