"""Módulo encargado del procesamiento gráfico, rasterización y ciclo de vida de activos de documentos temporales.

PyMuPDF y Pillow se importan de forma diferida, dentro del único método que los
usa. Es el mismo criterio que aplican `config/providers.py` con los SDK de los
proveedores de IA y `core/store_client.py` con el almacén: importar un módulo del
dominio no debe arrastrar sus dependencias pesadas. Aquí el efecto concreto es
que `core.orchestrator`, que importa esta clase, deja de exigir PyMuPDF instalado
para poder siquiera recolectar un test que nunca va a rasterizar nada.
"""
import os
import tempfile


class CVImageExtractor:
    """Componente encargado de la rasterización y limpieza de documentos PDF."""

    def _make_multiple_of_28(self, value: int) -> int:
        """Calcula el mayor múltiplo de 28 que no excede el valor, para evitar el bug de tensores de Qwen-VL en Ollama."""
        return (value // 28) * 28

    def pdf_to_images(self, pdf_path: str) -> list:
        """Convierte las páginas del PDF a imágenes matemáticamente compatibles con Qwen2.5-VL.

        Las imágenes se escriben en un directorio temporal ÚNICO por invocación
        (tempfile.mkdtemp), no con nombres fijos en el directorio de trabajo.
        Dos efectos deliberados: dos postulaciones simultáneas en el portal no
        pueden pisarse las páginas entre sí (el nombre fijo temp_page_N.png las
        hacía compartidas entre todos los usuarios del proceso), y nunca se
        sobreescribe un fichero de una ejecución anterior que otro proceso
        mantenga bloqueado, que en Windows aborta la extracción con
        "cannot remove file: Permission denied".
        """
        import fitz  # PyMuPDF
        from PIL import Image

        doc = fitz.open(pdf_path)
        image_paths = []

        # Mantenemos el escalado base para que Qwen lea con nitidez
        zoom_matrix = fitz.Matrix(1.5, 1.5)

        tmp_dir = tempfile.mkdtemp(prefix="cv_pages_")

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=zoom_matrix)

            output_path = os.path.join(tmp_dir, f"page_{page_num}.png")
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

        doc.close()
        return image_paths

    def clear_temp_images(self, image_paths: list):
        """Limpia los archivos gráficos temporales y su directorio de invocación.

        La limpieza es tolerante a fallos: un fichero bloqueado no debe tumbar
        la postulación, y un directorio que no quede vacío lo recogerá el
        sistema operativo con el resto del temporal.
        """
        directorios = set()
        for path in image_paths:
            directorios.add(os.path.dirname(path))
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"[LOG] No se pudo eliminar la imagen temporal {path}: {e}")

        for directorio in directorios:
            # Solo se retiran los directorios creados por este módulo.
            if directorio and os.path.basename(directorio).startswith("cv_pages_"):
                try:
                    os.rmdir(directorio)
                except OSError:
                    pass  # No vacío o bloqueado: no es motivo para fallar.