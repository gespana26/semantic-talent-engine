"""Modulo de la capa de presentacion encargado de gestionar la interfaz de linea de comandos (CLI) y sus menus."""

import json
import os
import threading

from config import settings
from core.auto_match import evaluar_y_notificar
from core.data_hygiene import email_valido, telefono_valido
from core.query_translator import QueryTranslator
from core.search_engine import CVSearchEngine
from core.vacancy_catalog import obtener_vacantes_publicas


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
        print("Puede registrar la vacante desde un PDF o pegando su texto.")

        raw_path = input("Ruta del PDF de la vacante (deje vacío para pegar el texto): ").strip().strip("'\"")

        pdf_path = None
        prompt_vacante = None

        if raw_path:
            for char_oculto in ["‪", "‬", "‎", "‏"]:
                raw_path = raw_path.replace(char_oculto, "")
            candidato_path = os.path.normpath(raw_path)
            if not os.path.exists(candidato_path) and os.path.exists(candidato_path + ".pdf"):
                candidato_path = candidato_path + ".pdf"
            if not os.path.exists(candidato_path):
                print(f"[ALERTA] No se encontro el archivo: '{candidato_path}'. Cancelando operacion.")
                return
            pdf_path = candidato_path
        else:
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
            resultado = self.orquestador_vacantes.process_and_register_vacancy(
                raw_text=prompt_vacante, pdf_path=pdf_path
            )
            
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

    def _elegir_vacante_destino(self):
        """Presenta el catálogo de vacantes vigentes y devuelve la colección elegida.

        La CLI comparte con el portal web la misma regla: el destino de una
        postulación se elige de un conjunto verificado, nunca se teclea. Escribirlo
        a mano permitía que un error tipográfico creara una colección nueva y sin
        oferta, en la que la postulación quedaba registrada sin que el auto-match
        pudiera encontrar criterio con el que compararla.

        Devuelve la cadena vacía para la bolsa global y None si el operador aborta.
        """
        vacantes = obtener_vacantes_publicas()

        print("\n  [0] Bolsa Global (sin vacante especifica)")
        for i, vacante in enumerate(vacantes, start=1):
            vigencia = f" — quedan {vacante['dias']} dias" if vacante['dias'] is not None else ""
            print(f"  [{i}] {vacante['titulo']}{vigencia}")

        if not vacantes:
            print("  (No hay vacantes vigentes publicadas.)")

        seleccion = input("Seleccione el destino de la postulacion [0]: ").strip() or "0"
        if not seleccion.isdigit() or int(seleccion) > len(vacantes):
            print("[ALERTA] Seleccion no valida. Operacion cancelada.")
            return None

        indice = int(seleccion)
        return "" if indice == 0 else vacantes[indice - 1]["coleccion"]

    def menu_postulacion_candidato(self):
        """Flujo de captura para el portal de postulacion del candidato (Formulario descriptivo mas CV)."""
        print("\n--- PASARELA CORPORATIVA: PORTAL DE CAPTACION TALENTO ---")
        nombre = input("Nombres y Apellidos: ").strip()
        correo = input("Direccion de Email de contacto: ").strip()
        telefono = input("Numero telefonico movil: ").strip()
        perfil_declarado = input("Extracto o declaracion profesional sumaria: ").strip()

        cargo_objetivo = self._elegir_vacante_destino()
        if cargo_objetivo is None:
            return


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
        # La CLI aplica el mismo contrato de identidad que el portal web: los
        # validadores son compartidos, de modo que ninguna ruta de ingesta puede
        # persistir un candidato sin canal de contacto utilizable.
        if not (nombre and correo and telefono and pdf_path):
            print("[ALERTA] Validacion de campos fallida (Nombre, Correo, Teléfono y CV son obligatorios).")
            return

        if not email_valido(correo):
            print("[ALERTA] El correo electronico no tiene un formato valido.")
            return

        if not telefono_valido(telefono):
            print("[ALERTA] El numero de contacto no es valido (entre 7 y 15 digitos).")
            return


        if not os.path.exists(pdf_path):
            print("[ALERTA] El archivo no fue encontrado en el sistema de archivos.")
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
                    target=evaluar_y_notificar,
                    args=(cargo_objetivo, res.get("datos_extraidos", {}), res.get("verificacion"))
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
        
        if not prompt_busqueda:
            return

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
            print("  REGISTROS DE COINCIDENCIA DE ALTA DENSIDAD (BOLSA GLOBAL DE TALENTO)")
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