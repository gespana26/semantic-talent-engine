"""Modulo de la capa de presentacion encargado de gestionar la interfaz de linea de comandos (CLI) y sus menus."""

import os
import json
import threading
from config import settings
from config.settings import clean_collection_name
from core.query_translator import QueryTranslator  
from core.search_engine import CVSearchEngine
from core.email_service import enviar_alerta_talento

# =====================================================================
# FUNCIÓN FANTASMA (SEGUNDO PLANO) PARA ALERTAS DE AFINIDAD
# =====================================================================
def evaluar_y_notificar_background(silo_destino, datos_extraidos):
    """Ejecuta un auto-match silencioso. Si el candidato es Top y >= 85%, alerta al reclutador."""
    try:
        if not silo_destino:
            return 
            
        coleccion_target = clean_collection_name(silo_destino)
        buscador = CVSearchEngine(collection_name=coleccion_target)
        texto_vacante = buscador.obtener_perfil_vacante()
        
        if not texto_vacante:
            return
            
        candidatos_top = buscador.search_candidates(query_text=texto_vacante, limit=10)
        
        correo_nuevo = str(datos_extraidos.get('correo_electronico', '')).lower().strip()
        nombre_nuevo = datos_extraidos.get('nombre_completo', 'Candidato Destacado')
        extracto = datos_extraidos.get('perfil_profesional', 'Extracto no disponible')[:250] + "..."
        
        for cand in candidatos_top:
            if cand.get('correo', '').lower().strip() == correo_nuevo:
                afinidad = cand.get('porcentaje_afinidad', 0)
                if afinidad >= 85.0:
                    enviar_alerta_talento(nombre_nuevo, silo_destino, afinidad, extracto)
                break 
                
    except Exception:
        pass # Silencioso en la consola para no interrumpir la experiencia del usuario


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
            
            # --- NUEVA SECCIÓN DE VISIBILIDAD DE DATOS ---
            print("\n" + "="*60)
            print("  PERFIL DE VACANTE ESTRUCTURADO POR IA (NORMALIZADO)")
            print("="*60)
            
            datos_mostrar = resultado.get("datos_extraidos", resultado)
            print(json.dumps(datos_mostrar, indent=2, ensure_ascii=False))
            print("="*60)
            
            operacion = resultado.get('operacion', 'EXITO').upper()
            coleccion = resultado.get('coleccion', 'Base Vectorial')
            print(f"\n[TRANSACCION COMPLETA] Estado Operativo: {operacion} | Catalogo Destino: {coleccion}")
            
        except Exception as e:
            print(f"\n[ERROR CRITICO] Fallo operacional en el pipeline transaccional de la vacante: {e}")

    def menu_postulacion_candidato(self):
        """Flujo de captura para el portal de postulacion del candidato (Formulario descriptivo mas CV)."""
        print("\n--- PASARELA CORPORATIVA: PORTAL DE CAPTACION TALENTO ---")
        nombre = input("Nombres y Apellidos: ").strip()
        correo = input("Direccion de Email de contacto: ").strip()
        telefono = input("Numero telefonico movil: ").strip()
        perfil_declarado = input("Extracto o declaracion profesional sumaria: ").strip()
        cargo_objetivo = input("Identificacion de nomenclatura del cargo destino (Deje vacío para Global): ").strip()
        
        raw_path = input("Ruta fisica local indexada al recurso PDF del CV: ").strip().strip("'\"")

        for char_oculto in ["\u202a", "\u202c", "\u200e", "\u200f"]:
            raw_path = raw_path.replace(char_oculto, "")
            
        pdf_path = os.path.normpath(raw_path)

        if not os.path.exists(pdf_path):
            nombre_base = os.path.basename(pdf_path)
            
            if os.path.exists(nombre_base):
                pdf_path = os.path.abspath(nombre_base)
            elif os.path.exists(pdf_path + ".pdf"):
                pdf_path = pdf_path + ".pdf"
            elif os.path.exists(nombre_base + ".pdf"):
                pdf_path = os.path.abspath(nombre_base + ".pdf")

        # Verificacion final post-curacion (cargo_objetivo ahora es opcional en la validación)
        if not (nombre and correo and telefono and pdf_path):
            print("[ALERTA] Validacion de campos fallida (Nombre, Correo, Teléfono y CV son obligatorios).")
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
            
            # 🚀 AQUÍ SE LANZA EL HILO EN SEGUNDO PLANO PARA LA CONSOLA CLI
            if cargo_objetivo.strip():
                hilo_alerta = threading.Thread(
                    target=evaluar_y_notificar_background,
                    args=(cargo_objetivo, res.get("datos_extraidos", {}))
                )
                hilo_alerta.start()
            # -------------------------------------------------------------
            
            print("\n" + "="*60)
            print("  DATOS EXTRAIDOS DEL CV (PROCESAMIENTO MULTIMODAL)")
            print("="*60)
            print(json.dumps(res["datos_extraidos"], indent=2, ensure_ascii=False))
            print("="*60)
            
            print(f"\n[TRANSACCION COMPLETA] Indexacion Dual Exitosa.\n -> Silo ID Referencial: {res.get('id_vacante_silo', 'N/A')}\n -> Global Ledger ID: {res['id_bolsa_global']}")
        except Exception as e:
            print(f"\n[ERROR CRITICO] Quiebre de secuencia en pipeline multimodal de candidato: {e}")

    def menu_buscar_candidatos(self):
        """Interfaz del buscador conceptual para ejecutar consultas de busqueda semantica hibrida RAG."""
        print("\n--- PASARELA CORPORATIVA: BUSCADOR DE TALENTO GLOBAL ---")
        prompt_busqueda = input("Indique los criterios semanticos avanzados y restricciones duras requeridas:\n> ").strip()
        
        if not prompt_busqueda: return

        print("\n[OPERACION - RUNTIME] Traduciendo requerimientos verbales a arboles booleanos indexables...")
        try:
            traductor = QueryTranslator()
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
            
            print("\n" + "="*70)
            print(f"  REGISTROS DE COINCIDENCIA DE ALTA DENSIDAD (BOLSA GLOBAL DE TALENTO)")
            print("="*70)
            
            if not candidatos:
                print("Cero registros matematicos computados para los criterios evaluados.")
            else:
                for idx, cand in enumerate(candidatos, 1):
                    # Extraemos el JSON completo que ahora viene enriquecido
                    json_data = cand.get('perfil_completo_json', {})
                    
                    print(f"\nIndice Ranking #{idx} - [METRICA MATCH HUMANO: {cand['porcentaje_afinidad']}%]")
                    print(f"  • Identidad: {cand['nombre']} | {cand['correo']}")
                    
                    # --- NUEVA INFORMACIÓN EN PANTALLA ---
                    nivel_acad = json_data.get('nivel_academico_maximo', 'No especificado')
                    experiencia = json_data.get('anios_experiencia_total', 0)
                    print(f"  • Nivel Academico: {nivel_acad}")
                    print(f"  • Experiencia Total: {experiencia} años consolidados")
                    print(f"  • Puntero Fisico: {cand['pdf_origen']}")
                    
                    # Truncamos el perfil a 150 caracteres para mantener la consola limpia
                    perfil = json_data.get('perfil_profesional', 'No disponible')
                    perfil_truncado = perfil[:150] + "..." if len(perfil) > 150 else perfil
                    print(f"  • Extracto Perfil: {perfil_truncado}")
                    print("-" * 70)
                    
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