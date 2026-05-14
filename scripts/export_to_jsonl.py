import os
import sys
import json
from datetime import datetime
from sqlmodel import Session, select

# Añadir el directorio del backend al path del sistema para importaciones correctas
sys.path.append(os.getcwd())

from utils.logger import logger
from database import engine
from models import Session as TherapySession, AISuggestionLog, Psychologist, Patient

def export_sessions_to_jsonl():
    """
    Exporta las interacciones asistidas por IA de todas las sesiones
    a un archivo JSON Lines (.jsonl) con el formato solicitado.
    """
    try:
        logger.info("Iniciando la exportación de interacciones de sesiones a JSONL...")
        
        with Session(engine) as db:
            # 1. Obtener todos los logs de sugerencias de IA de la base de datos y cargarlos en memoria para acceso rápido
            logger.info("Cargando logs de sugerencias de IA de la base de datos...")
            ai_logs = {log.id: log for log in db.exec(select(AISuggestionLog)).all()}
            logger.info(f"Se cargaron {len(ai_logs)} registros de sugerencias de IA.")
            
            # Cargar terapeutas y pacientes para mapear nombres y números de caso
            logger.info("Cargando terapeutas y pacientes de la base de datos...")
            therapists = {t.id: t.name for t in db.exec(select(Psychologist)).all()}
            patients = {p.id: p.patient_code for p in db.exec(select(Patient)).all()}
            
            # 2. Obtener todas las sesiones de terapia activas
            logger.info("Cargando sesiones de la base de datos...")
            sessions = db.exec(select(TherapySession).where(TherapySession.deleted_at == None)).all()
            
            if not sessions:
                logger.warning("No se encontraron sesiones en la base de datos.")
                return
                
            logger.info(f"Se encontraron {len(sessions)} sesiones activas para procesar.")
            
            # 3. Procesar sesiones e interacciones
            exported_count = 0
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"sessions_export_{timestamp}.jsonl"
            
            logger.info(f"Creando archivo JSONL '{output_filename}'...")
            with open(output_filename, "w", encoding="utf-8") as f:
                for session in sessions:
                    if not session.chat_snapshot:
                        continue
                    
                    terapeuta_nombre = therapists.get(session.psychologist_id, "Desconocido") if session.psychologist_id else "Desconocido"
                    numero_caso = patients.get(session.patient_id, "Desconocido") if session.patient_id else "Desconocido"
                    
                    # Guardamos el texto del último mensaje del paciente para asociarlo como 'paciente_input'
                    last_patient_text = ""
                    last_sender = None
                    
                    for msg in session.chat_snapshot:
                        sender = msg.get("sender")
                        text = msg.get("text", "")
                        
                        if sender == "patient":
                            if last_sender == "patient":
                                if last_patient_text:
                                    last_patient_text += "\n" + text
                                else:
                                    last_patient_text = text
                            else:
                                last_patient_text = text
                        elif sender == "therapist":
                            ai_log_id = msg.get("ai_suggestion_log_id")
                            
                            # Si este mensaje del terapeuta usó o generó sugerencias de IA
                            if ai_log_id is not None:
                                ai_log = ai_logs.get(ai_log_id)
                                if ai_log:
                                    # Determinar la opción elegida (final_option_id)
                                    opcion_elegida = ai_log.final_option_id
                                    
                                    # Recuperación de fallback: si final_option_id no está guardado,
                                    # intentamos deducirlo comparando el texto final con las alternativas generadas
                                    if opcion_elegida is None:
                                        if text == ai_log.suggestion_model1:
                                            opcion_elegida = 1
                                        elif text == ai_log.suggestion_model2:
                                            opcion_elegida = 2
                                        elif text == ai_log.suggestion_model3:
                                            opcion_elegida = 3
                                    
                                    # Determinar edición humana: si se editó, se pone el texto final enviado,
                                    # si se envió la sugerencia tal cual, se pone vacío/None (no hubo edición)
                                    was_edited = msg.get("was_edited_by_human", False)
                                    edicion_humana = text if was_edited else ""
                                    
                                    tacticas_generadas = []
                                    if ai_log.suggested_strategies:
                                        try:
                                            tacticas_generadas = json.loads(ai_log.suggested_strategies)
                                        except Exception:
                                            tacticas_generadas = [ai_log.suggested_strategies]
                                            
                                    tactica_elegida_str = ai_log.selected_strategy or ""
                                    tactica_elegida_pos = None
                                    if tactica_elegida_str and tactica_elegida_str in tacticas_generadas:
                                        tactica_elegida_pos = tacticas_generadas.index(tactica_elegida_str) + 1
                                        
                                    modelos_utilizados = []
                                    if ai_log.models_used:
                                        try:
                                            modelos_utilizados = json.loads(ai_log.models_used)
                                        except Exception:
                                            modelos_utilizados = [ai_log.models_used]
                                    
                                    # Estructuramos el JSON plano para facilitar el entrenamiento y análisis
                                    session_data = {
                                        "sesion_id": session.id,
                                        "terapeuta_nombre": terapeuta_nombre,
                                        "numero_caso": numero_caso,
                                        "fecha": ai_log.created_at.strftime("%Y-%m-%d %H:%M:%S") if ai_log.created_at else session.date.strftime("%Y-%m-%d %H:%M:%S"),
                                        "paciente_input": last_patient_text,
                                        "instrucciones_ia": ai_log.ai_instructions_used or "",
                                        "tacticas_generadas": tacticas_generadas,
                                        "tactica_elegida": tactica_elegida_pos,
                                        "modelos_utilizados": modelos_utilizados,
                                        "ia_alternativa_1": ai_log.suggestion_model1,
                                        "ia_alternativa_2": ai_log.suggestion_model2,
                                        "ia_alternativa_3": ai_log.suggestion_model3,
                                        "opcion_elegida": opcion_elegida,
                                        "edicion_humana": edicion_humana
                                    }
                                    
                                    # Escribir la línea asegurando mantener caracteres españoles legibles (utf-8 sin escapar)
                                    f.write(json.dumps(session_data, ensure_ascii=False) + "\n")
                                    exported_count += 1
                                    
                        last_sender = sender
                                    
            abs_path = os.path.abspath(output_filename)
            logger.success("¡La exportación a JSONL se ha completado con éxito!")
            logger.success(f"Se han exportado {exported_count} interacciones asistidas por IA.")
            logger.success(f"Archivo JSONL guardado en: {abs_path}")
            
            print(f"\n" + "="*60)
            print(f" ÉXITO: Exportación de Interacciones a JSONL")
            print(f" Ruta del archivo: {abs_path}")
            print(f" Total de interacciones exportadas: {exported_count}")
            print("="*60 + "\n")
            
    except Exception as e:
        logger.error(f"Error crítico durante la exportación a JSONL: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    export_sessions_to_jsonl()
