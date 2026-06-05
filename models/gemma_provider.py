import json
import re
import ollama
from typing import Dict, Any, List
from .interfaces import BaseLLMProvider
from config import settings

class GemmaMultimodalProvider(BaseLLMProvider):
    """Proveedor local de IA que implementa capacidades multimodales

    y auto-corrección de JSONs malformados.
    """
    
    def __init__(self):
        self.model_name = settings.MODEL_NAME
        self.system_prompt = settings.SYSTEM_PROMPT

    def _clean_llm_response(self, raw_content: str) -> str:
        """Elimina posibles bloques de código markdown (```json ... ```) 

        o espacios en blanco corruptos que confunden al parser.
        """
        cleaned = raw_content.strip()
        # Eliminar marcas de código markdown si el modelo las incluyó por error
        cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        return cleaned.strip()

    def _attempt_self_correction(self, broken_json_text: str, error_message: str) -> Dict[str, Any]:
        """CAPA DE AUTO-CORRECCIÓN: Pide al modelo reparar los delimitadores 

        del JSON dañado sin volver a procesar las imágenes pesadas.
        """
        print(f"[IA - ADVERTENCIA] JSON malformado detectado. Iniciando auto-corrección...")
        
        correction_prompt = f"""
        El siguiente texto debería ser un objeto JSON válido pero tiene un error de sintaxis: "{error_message}".
        
        Tu única tarea es corregir la sintaxis del JSON (reparar comillas internas, comas faltantes, llaves) 
        para que pueda ser procesado por json.loads() en Python. No alteres la información del candidato.
        
        TEXTO COMPROMETIDO:
        {broken_json_text}
        
        CRÍTICO: Devuelve única y exclusivamente el JSON corregido y limpio, sin textos adicionales.
        """
        
        # Llamada rápida de texto a texto (sin imágenes) para reparar la sintaxis
        response = ollama.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": correction_prompt}],
            format="json"
        )
        
        corrected_content = self._clean_llm_response(response["message"]["content"])
        return json.loads(corrected_content)

    def parse_cv_images_to_json(self, image_paths: List[str]) -> Dict[str, Any]:
        raw_content = ""
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": "Analiza visualmente estas páginas de currículum y extrae su información estructurada en el formato JSON estricto.",
                    "images": image_paths
                }
            ]

            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                format="json"
            )

            raw_content = response["message"]["content"]
            
            # 1. Limpieza inicial de la cadena
            cleaned_content = self._clean_llm_response(raw_content)
            
            # 2. Intentar parsear el JSON estándar
            return json.loads(cleaned_content)

        except json.JSONDecodeError as json_error:
            # 3. Si falla el parseo por delimitadores (tu error actual), se activa la auto-corrección
            print(f"[IA - ERROR SINTAXIS] Falló la lectura directa: {json_error}")
            try:
                return self._attempt_self_correction(raw_content, str(json_error))
            except Exception as e:
                raise RuntimeError(f"La auto-corrección de JSON también falló: {str(e)}")
                
        except Exception as e:
            raise RuntimeError(f"Error en inferencia multimodal con Gemma 4: {str(e)}")