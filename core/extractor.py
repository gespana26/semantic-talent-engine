"""Módulo encargado del procesamiento gráfico, rasterización y ciclo de vida de activos de documentos temporales."""

import os
import fitz  # PyMuPDF

class CVImageExtractor:
    """Administra pipelines de rasterización de alta fidelidad desde documentos portátiles digitales hacia estructuras de arrays de visión."""
    
    def __init__(self, output_dir="./temp_cv_images/"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def pdf_to_images(self, pdf_path: str) -> list:
        """Transforma cada índice de página de un PDF en un archivo PNG de alta densidad optimizado para modelos de visión OCR.

        Args:
            pdf_path (str): Ruta absoluta o relativa del sistema de archivos hacia el documento origen.

        Returns:
            list: Colección de rutas del sistema que apuntan a los buffers de imagen PNG generados.
        """
        doc = fitz.open(pdf_path)
        image_paths = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Renderizado matricial a 300 DPI (Fuerza el factor de escala para mantener resolución óptima de visión)
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            output_path = os.path.join(self.output_dir, f"page_{page_num}_{os.path.basename(pdf_path)}.png")
            pix.save(output_path)
            image_paths.append(output_path)
            
        return image_paths

    def clear_temp_images(self, image_paths: list):
        """Purga activos gráficos para prevenir el desbordamiento de almacenamiento, condicionando operaciones según los flags del entorno."""
        from config import settings
        
        if settings.DEBUG_MODE:
            print("[INFO - OBSERVABILIDAD] Variable debug activa: Reteniendo matrices PNG temporales para verificación visual.")
            return

        for path in image_paths:
            if os.path.exists(path):
                os.remove(path)
        print("[INFO - MOTOR] Almacenamiento temporal de disco purgado exitosamente.")