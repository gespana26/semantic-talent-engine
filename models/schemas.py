"""Capa de validacion de datos que define los contratos inmutables para los pipelines de extraccion de IA mediante Pydantic."""

from typing import List

from pydantic import BaseModel, Field


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
    empresa: str = Field(default="", description="Razon social de la organizacion.")
    cargo: str = Field(default="", description="Titulo del rol desempenado.")
    duracion_anios: float = Field(default=0.0, description="Duracion en la empresa en años (ej. 2.5)")
    # `database.py` leia este campo desde el principio, pero el esquema no lo
    # definia, de modo que el historial vectorizado quedaba como
    # "- Data Engineer en Acme (3.5 años):" sin decir que hizo la persona. El
    # embedding se calculaba entonces sobre cargos y empresas, dejando fuera las
    # responsabilidades y los logros, que es donde vive la señal discriminante.
    responsabilidades: str = Field(
        default="",
        description="Principales responsabilidades y logros en el puesto, en una o dos frases."
    )

class CandidateStructure(BaseModel):
    """Contrato de la *extraccion*, no de la *identidad*.

    Todos los campos declaran un valor por defecto de forma deliberada. El
    esquema estricto que el SDK de OpenAI deriva de esta clase sigue exigiendo
    la clave completa al modelo (`required` incluye todas las propiedades), de
    modo que la ruta de Structured Outputs no se debilita. Los defaults
    protegen la ruta local de Ollama, donde el JSON se valida con
    `model_validate_json`: la omision de un campo de contenido degrada ese
    campo en lugar de tumbar la postulacion entera.

    La obligatoriedad de los datos de identidad (nombre, correo) no se resuelve
    aqui sino en el paso de confirmacion del formulario, donde el dato es
    verificable y no probabilistico.
    """
    # --- Nivel 1: identidad. Se confirman en el formulario, no se imponen al extractor. ---
    nombre_completo: str = Field(default="", description="Nombre y apellidos del candidato. Cadena vacia si no aparece en el documento.")
    correo_electronico: str = Field(default="", description="Correo de contacto. Cadena vacia si no aparece en el documento; nunca inferido.")
    telefono_movil: str = Field(default="", description="Telefono de contacto. Cadena vacia si no aparece en el documento; nunca inferido.")
    ubicacion: str = Field(default="No especificada")
    # --- Nivel 2: contenido. Degradan con elegancia, nunca bloquean. ---
    nivel_academico_maximo: str = Field(default="", description="Nombre exacto del titulo obtenido. Ej: Ingeniero Industrial, Administrador de Empresas, Industrial Engineer")
    educacion_detalle: List[str] = Field(default_factory=list, description="Lista de titulos o cursos formales")
    anios_experiencia_total: int = Field(default=0, description="Suma total de años de experiencia profesional (numero entero)")
    historial_laboral: List[ExperienciaLaboral] = Field(default_factory=list)
    perfil_profesional: str = Field(default="")
    hard_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)

class ChromaQueryStructure(BaseModel):
    """Contrato de datos que representa una estructura de consulta compilada y optimizada para busquedas hibridas vector/metadatos."""
    query_text_conceptual: str = Field(description="Abstraccion de texto purificada para la generacion de vectores densos de alta proximidad.")
    where_filter: dict = Field(description="Objeto de consulta estructurado compatible con el esquema relacional de filtros de ChromaDB.")