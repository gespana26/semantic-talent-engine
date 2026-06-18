"""Modulo de la capa de presentacion encargado de gestionar la interfaz de linea de comandos (CLI) y sus menus."""

import os
import json
from config import settings
from core.query_translator import QueryTranslator  # <-- CORREGIDO: Importacion alineada al nuevo motor dinamico
from core.search_engine import CVSearchEngine

class RECRUITMENTConsoleApp:
    """Controlador de la interfaz de usuario que orquesta el flujo visual de la consola CLI."""
    
    def __init__(self, vacancy_orchestrator, candidate_orchestrator):
        """Inyecta los orquestadores de negocio necesarios para operar los menus de la aplicacion."""
        self.orquestador_vacantes = vacancy_orchestrator
        self.orquestador_candidatos = candidate_orchestrator

    def mostrar_menu_principal(self):
        """Muestra la pasarela principal de opciones del sistema ATS."""
        print("\n" + "="*60)
        print("      SISTEMA AGENTE IA - ATS PARA RECRUITMENT (CORE)")
        print("="*60)
        print(f"[ENV] Proveedor IA: {settings.AI_PROVIDER_TYPE.upper()} | Modelo Target: {settings.MODEL_NAME}")
        print(f"[LOG] Modo Debug (Telemetria Activa): {settings.DEBUG_MODE}")
        print("-" * 60)
        print("1. [RECRUITER] Ingestar / Editar Vacante Operativa (Natural Query)")
        print("2. [CANDIDATO] Postulacion Web Portal (Transactional Form + CV)")
        print("3. [RECRUITER] Buscador Semantico Cruzado (Hybrid RAG Vector Search)")
        print("4. Terminar Ejecucion")
        print("="*60)
        return input("Seleccione una opcion de la pasarela de control (1-4): ").strip()

    def menu_registrar_vacante(self):
        """Gestiona el flujo de captura multilinea para la creacion o edicion de ofertas de empleo."""
        print("\n--- PASARELA CORPORATIVA: REGISTRO RECRUITMENT INTERFACE ---")
        print("Consigne los parametros de perfilacion corporativa en bloque de texto continuo.")
        print("(Pegue el texto libremente y escriba la palabra 'FIN' en una linea nueva para procesar):")
        
        lineas = []
        while True:
            linea = input().strip()
            if linea.upper() == "FIN":
                break
            lineas.append(linea)
            
        prompt_vacante = "\n".join(lineas).strip()
        
        if not prompt_vacante:
            print("[ALERTA] Entrada vacia. Cancelando operacion.")
            return

        print("\n[OPERACION - RUNTIME] Decodificando bloque linguistico y estructurando indices...")
        try:
            resultado = self.orquestador_vacantes.process_and_register_vacancy(raw_text=prompt_vacante)
            print(f"\n[TRANSACCION COMPLETA] Estado Operativo: {resultado['operacion'].upper()} | Catalogo Destino: {resultado['coleccion']}")
        except Exception as e:
            print(f"\n[ERROR CRITICO] Fallo operacional en el pipeline transaccional de la vacante: {e}")

    def menu_postulacion_candidato(self):
        """Flujo de captura para el portal de postulacion del candidato (Formulario descriptivo mas CV)."""
        print("\n--- PASARELA CORPORATIVA: PORTAL DE CAPTACION TALENTO ---")
        nombre = input("Nombres y Apellidos: ").strip()
        correo = input("Direccion de Email de contacto: ").strip()
        telefono = input("Numero telefonico movil: ").strip()
        perfil_declarado = input("Extracto o declaracion profesional sumaria: ").strip()
        cargo_objetivo = input("Identificacion de nomenclatura del cargo destino: ").strip()
        
        raw_path = input("Ruta fisica local indexada al recurso PDF del CV: ").strip().strip("'\"")

        for char_oculto in ["\u202a", "\u202c", "\u200e", "\u200f"]:
            raw_path = raw_path.replace(char_oculto, "")
            
        pdf_path = os.path.normpath(raw_path)

        # --- PIPELINE DE AUTO-CURACION PARA VALIDACION EN WINDOWS ---
        if not os.path.exists(pdf_path):
            nombre_base = os.path.basename(pdf_path) # Extrae solo '1_HV_LUIS_FERNANDO.pdf'
            
            # Intento 1: ¿El archivo esta en la misma carpeta desde donde corre el programa?
            if os.path.exists(nombre_base):
                pdf_path = os.path.abspath(nombre_base)
            
            # Intento 2: ¿Tiene el problema de la doble extension oculta (.pdf.pdf)?
            elif os.path.exists(pdf_path + ".pdf"):
                pdf_path = pdf_path + ".pdf"
                
            # Intento 3: ¿Esta en la misma carpeta Y ADEMAS tiene doble extension (.pdf.pdf)?
            elif os.path.exists(nombre_base + ".pdf"):
                pdf_path = os.path.abspath(nombre_base + ".pdf")

        # Verificacion final post-curacion
        if not (nombre and correo and telefono and cargo_objetivo and pdf_path):
            print("[ALERTA] Validacion de campos fallida.")
            return
            
        if not os.path.exists(pdf_path):
            print(f"[ALERTA] El archivo no fue encontrado en el sistema de archivos.")
            print(f"  -> Python busco de forma literal: '{pdf_path}'")
            return

        datos_formulario = {"nombre": nombre, "correo": correo, "telefono": telefono, "perfil": perfil_declarado}

        print("\n[OPERACION - RUNTIME] Ejecutando guardado fisico desacoplado y enrutamiento de doble indice...")
        try:
            res = self.orquestador_candidatos.process_and_register_candidate(
                pdf_path=pdf_path, cargo_objetivo=cargo_objetivo, datos_formulario=datos_formulario
            )
            
            print("\n" + "="*60)
            print("  DATOS EXTRAIDOS DEL CV (PROCESAMIENTO MULTIMODAL)")
            print("="*60)
            print(json.dumps(res["datos_extraidos"], indent=2, ensure_ascii=False))
            print("="*60)
            
            print(f"\n[TRANSACCION COMPLETA] Indexacion Dual Exitosa.\n -> Silo ID Referencial: {res['id_vacante_silo']}\n -> Global Ledger ID: {res['id_bolsa_global']}")
        except Exception as e:
            print(f"\n[ERROR CRITICO] Quiebre de secuencia en pipeline multimodal de candidato: {e}")

    def menu_buscar_candidatos(self):
        """Interfaz del buscador conceptual para ejecutar consultas de busqueda semantica hibrida RAG."""
        print("\n--- PASARELA CORPORATIVA: BUSCADOR DE TALENTO GLOBAL ---")
        prompt_busqueda = input("Indique los criterios semanticos avanzados y restricciones duras requeridas:\n> ").strip()
        
        if not prompt_busqueda: return

        print("\n[OPERACION - RUNTIME] Traduciendo requerimientos verbales a arboles booleanos indexables...")
        try:
            traductor = QueryTranslator()  # <-- CORREGIDO: Instanciacion limpia de la clase global
            query_estructurada = traductor.translate_prompt_to_chroma(prompt_busqueda)
            
            if settings.DEBUG_MODE:
                print("\n[LOG DE TELEMETRIA - INTENT TRANSLATOR]")
                print(f"  • Contenido del Foco Vectorial: '{query_estructurada.query_text_conceptual}'")
                print(f"  • Filtro Relacional de Datos: {json.dumps(query_estructurada.where_filter, indent=2)}")
            
            buscador = CVSearchEngine(collection_name="talento-global-empresa")
            filtro = query_estructurada.where_filter if query_estructurada.where_filter else None
            
            candidatos = buscador.search_candidates(
                query_text=query_estructurada.query_text_conceptual, limit=3, where_filter=filtro
            )
            
            print("\n" + "="*60)
            print(f"  REGISTROS DE COINCIDENCIA DE ALTA DENSIDAD (BOLSA GLOBAL DE TALENTO)")
            print("="*60)
            
            if not candidatos:
                print("Cero registros matematicos computados para los criterios evaluados.")
            else:
                for idx, cand in enumerate(candidatos, 1):
                    print(f"Indice Ranking #{idx} - [METRICA MATCH HUMANO: {cand['porcentaje_afinidad']}%]")
                    print(f"  • Identidad: {cand['nombre']} | Canal de comunicacion: {cand['correo']}")
                    print(f"  • Puntero Fisico de Archivo: {cand['pdf_origen']}")
                    print(f"  • Entidad Perfil Unificado: {cand['perfil_completo_json'].get('perfil_profesional')}")
                    print("-" * 60)
        except Exception as e:
            print(f"\n[ERROR CRITICO] Error de ejecucion en motor de busqueda vectorial hibrido: {e}")

    def run(self):
        """Arranca el bucle de control operativo interactivo de la consola CLI."""
        while True:
            opcion = self.mostrar_menu_principal()
            if opcion == "1":
                self.menu_registrar_vacante()
            elif opcion == "2":
                self.menu_postulacion_candidato()
            elif opcion == "3":
                self.menu_buscar_candidatos()
            elif opcion == "4":
                print("\nFinalizando procesos corporativos del demonio core. Apagado completo.")
                break
            else:
                print("\n[ALERTA] Entrada de opcion no valida o corrupta.")
            input("\nPresione la tecla Intro para retornar a la pasarela principal...")