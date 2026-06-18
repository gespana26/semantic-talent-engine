"""Capa de validacion de datos que define los contratos inmutables para los pipelines de extraccion de IA mediante Pydantic."""

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

class CandidateStructure(BaseModel):
    """Contrato de datos que representa un perfil profesional extraido y normalizado desde un Curriculum Vitae."""
    nombre_completo: str = Field(description="Nombre y apellidos legales extraidos del documento del candidato.")
    correo_electronico: str = Field(description="Direccion de correo electronico principal de contacto detectada en el perfil.")
    telefono_movil: str = Field(description="Numero de telefono movil parsed de los detalles de contacto del perfil.")
    perfil_profesional: str = Field(description="Resumen analitico que sintetiza la trayectoria profesional, seniority y enfoque del candidato.")
    hard_skills: list[str] = Field(description="Inventario de competencias tecnicas locales, plataformas y habilidades duras identificadas.")
    soft_skills: list[str] = Field(description="Inventario de atributos conductuales locales, habilidades sociales y competencias blandas identificadas.")

class ChromaQueryStructure(BaseModel):
    """Contrato de datos que representa una estructura de consulta compilada y optimizada para busquedas hibridas vector/metadatos."""
    query_text_conceptual: str = Field(description="Abstraccion de texto purificada para la generacion de vectores densos de alta proximidad.")
    where_filter: dict = Field(description="Objeto de consulta estructurado compatible con el esquema relacional de filtros de ChromaDB.")