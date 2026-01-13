from llm_service import mi_modelo, generate_response_options
import os
from dotenv import load_dotenv

# Cargar variables de entorno por si acaso, aunque llm_service ya lo hace
load_dotenv()

def test_connection():
    print("--- Probando conexión con el LLM (Opción simple) ---")
    
    # Verificar si existe la API KEY
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ADVERTENCIA: No se encontró OPENAI_API_KEY en las variables de entorno.")
    else:
        print("API Key encontrada.")

    try:
        print("Enviando solicitud simple...")
        response = mi_modelo("Hola, ¿estás funcionando?", context="Responde brevemente con 'Sí, estoy funcionando'.")
        print("\n--- Respuesta del Modelo ---")
        print(response)
        print("----------------------------")
    except Exception as e:
        print(f"\nERROR: No se pudo conectar con el modelo. Detalles: {e}")

def test_response_options():
    print("\n--- Probando Generación de Opciones de Respuesta ---")
    
    historial_simulado = [
        {"role": "user", "content": "Me siento muy agobiado últimamente."},
        {"role": "assistant", "content": "¿Quieres contarme más sobre lo que te está agobiando?"},
        {"role": "user", "content": "Es el trabajo. Mi jefe me presiona mucho y siento que no puedo con todo."}
    ]
    
    try:
        print("Generando opciones para historial simulado...")
        opciones = generate_response_options(historial_simulado)
        print("\n--- Opciones Generadas ---")
        for i, opcion in enumerate(opciones, 1):
            print(f"Opción {i}: {opcion}")
        print("--------------------------")
    except Exception as e:
        print(f"ERROR: Falló la generación de opciones. Detalles: {e}")

if __name__ == "__main__":
    test_connection()
    test_response_options()
