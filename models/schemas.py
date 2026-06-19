"""Capa de validacion de datos que define los contratos inmutables para los pipelines de extraccion de IA mediante Pydantic."""

from pydantic import BaseModel, Field
from typing import List, Optional

class VacancyStructure(BaseModel):
    """Contrato de datos que representa una oferta de empleo corporativa completamente normalizada."""
    titulo_cargo: str = Field(description="Nomenclatura oficial del puesto de trabajo o cargo.")
    perfil_general: str = Field(description="Resumen ejecutivo del rol y sus responsabilidades operacionales centrales.")
    estudios_requeridos: list[str] = Field(description="Formacion academica, titulos profesionales o certificaciones requeridas.")
    experiencia_minima_anos: int = Field(description="Cantidad minima de anos de experiencia profesional requeridos en roles equivalentes.")
    rango_salarial: str = Field(description="Presupuesto asignado o banda de compensacion economica. Por defecto 'No especificado'.")
    hard_skills: list[str] = Field(description="Inventario de competencias tecnicas, lenguajes de programacion o herramientas de uso obligatorio.")
    soft_skills: list[str] = Field(description="Competencias conductuales y habilidades interpersonales requeridas para el perfil ideal.")
    dias_vigencia: int = Field(default=30, description="Duracion del ciclo de vida en dias para la publicacion activa de la vacante.")

class ExperienciaLaboral(BaseModel):
    empresa: str
    cargo: str
    duracion_anios: float = Field(description="Duracion en la empresa en años (ej. 2.5)")

class CandidateStructure(BaseModel):
    nombre_completo: str
    correo_electronico: str
    telefono_movil: str
    ubicacion: str = Field(default="No especificada")
    nivel_academico_maximo: str = Field(description="Ej: Bachiller, Profesional, Especializacion, Maestria")
    educacion_detalle: List[str] = Field(description="Lista de titulos o cursos formales")
    anios_experiencia_total: int = Field(description="Suma total de años de experiencia profesional (numero entero)")
    historial_laboral: List[ExperienciaLaboral]
    perfil_profesional: str
    hard_skills: List[str]
    soft_skills: List[str]

class ChromaQueryStructure(BaseModel):
    """Contrato de datos que representa una estructura de consulta compilada y optimizada para busquedas hibridas vector/metadatos."""
    query_text_conceptual: str = Field(description="Abstraccion de texto purificada para la generacion de vectores densos de alta proximidad.")
    where_filter: dict = Field(description="Objeto de consulta estructurado compatible con el esquema relacional de filtros de ChromaDB.")