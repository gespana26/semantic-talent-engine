from pydantic import BaseModel, Field
from typing import List, Dict, Any

class VacancyStructure(BaseModel):
    """Esquema rígido para la extracción de ofertas de empleo por la IA."""
    titulo_cargo: str = Field(description="Nombre oficial del puesto de trabajo.")
    perfil_general: str = Field(description="Resumen o descripción introductoria del rol y responsabilidades.")
    estudios_requeridos: List[str] = Field(description="Nivel educativo, carreras o certificaciones solicitadas.")
    experiencia_minima_anos: int = Field(description="Cantidad de años de experiencia mínimos requeridos.")
    rango_salarial: str = Field(description="Presupuesto o sueldo ofrecido. Colocar 'No especificado' si no se menciona.")
    hard_skills: List[str] = Field(description="Habilidades técnicas, lenguajes o herramientas obligatorias.")
    soft_skills: List[str] = Field(description="Habilidades blandas o competencias conductuales del candidato.")
    dias_vigencia: int = Field(default=30, description="Días que estará activa la vacante. Por defecto asume 30.")

class ChromaQueryStructure(BaseModel):
    """Esquema de traducción de requerimientos de lenguaje natural a sintaxis ChromaDB."""
    query_text_conceptual: str = Field(description="Conceptos abstractos purificados para la búsqueda semántica.")
    where_filter: Dict[str, Any] = Field(description="Diccionario lógico con operadores $and o $contains basados en metadatos.")