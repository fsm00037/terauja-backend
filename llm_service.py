from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_PSICOUJA"),
    base_url=os.getenv("BASE_URL_MODELS_PSICOUJA")
)

def clean_messages(messages):
    """
    Normaliza la lista de mensajes combinando roles consecutivos repetidos
    para evitar errores de validación en los LLMs.
    """
    if not messages:
        return []
    
    cleaned = []
    for msg in messages:
        if cleaned and cleaned[-1]['role'] == msg['role']:
            # Si el rol es el mismo que el anterior, concatenamos el contenido
            cleaned[-1]['content'] += f" {msg['content']}"
        else:
            cleaned.append(dict(msg)) # Copia para no modificar el original
    return cleaned

def llm_models(messages):
    """
    Llama a los modelos LLM usando OpenAI y devuelve la respuesta.
    """
    url_prefix = os.getenv("URL_MODELS_PSICOUJA", "")
    if not url_prefix:
        print("WARNING: URL_MODELS_PSICOUJA is not set in .env")

    # Normalizamos los mensajes antes de enviarlos
    safe_messages = clean_messages(messages)

    content_model1 = None
    content_model2 = None
    content_model3 = None

    # Llama
    try:
        response_model1 = client.chat.completions.create(
            model=url_prefix + "meta-llama/Llama-3.1-8B-Instruct",
            messages=safe_messages,
            max_tokens=256,
            temperature=0.7
        )
        content_model1 = response_model1.choices[0].message.content.strip()
    except Exception as ex:
        print(f"############# Error calling Llama: {ex}")

    # Gemma
    try:
        response_model2 = client.chat.completions.create(
            model=url_prefix + "google/gemma-3-12b-it",
            messages=safe_messages,
            max_tokens=256,
            temperature=0.7
        )
        content_model2 = response_model2.choices[0].message.content.strip()
    except Exception as ex:
        print(f"############# Error calling Gemma: {ex}")

    # Qwen
    try:
        response_model3 = client.chat.completions.create(
            model=url_prefix + "Qwen/Qwen3-8B",
            messages=safe_messages,
            max_tokens=256,
            temperature=0.7,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content_model3 = response_model3.choices[0].message.content.strip()
    except Exception as ex:
        print(f"############# Error calling Qwen: {ex}")
    
    return content_model1, content_model2, content_model3

def clean_response(text):
    """
    Limpia la respuesta del modelo eliminando prefijos comunes y texto no deseado.
    """
    if not text:
        return ""
    
    # Remover prefijos comunes
    prefixes_to_remove = [
        "Sugerencia de respuesta:",
        "Opción:",
        "Respuesta:",
        "1.", "2.", "3.",
        "Thinking:",
        "**Thinking**",
        "<thinking>",
        "</thinking>"
    ]
    
    cleaned = text.strip()
    
    for prefix in prefixes_to_remove:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    
    # Remover bloques de thinking si existen
    if "<thinking>" in cleaned and "</thinking>" in cleaned:
        import re
        cleaned = re.sub(r'<thinking>.*?</thinking>', '', cleaned, flags=re.DOTALL)
    
    # Remover asteriscos de markdown
    cleaned = cleaned.replace("**", "").replace("*", "")
    
    # Remover saltos de línea excesivos
    cleaned = " ".join(cleaned.split())
    
    return cleaned.strip()

def generate_response_options(chat_history, therapist_style=None, therapist_tone=None, therapist_instructions=None):
    
    # Construir el mensaje del sistema
    system_message = """Eres un psicólogo profesional en una sesión terapéutica. Estás conversando con un paciente y debes continuar la conversación de manera natural y terapéutica.
    IMPORTANTE: 
    - Responde SOLO con lo que dirías al paciente, sin explicaciones adicionales
    - NO incluyas prefijos como "Psicólogo:", "Respuesta:" o similares
    - Tu respuesta debe ser una continuación natural de la conversación"""
    
    # Añadir configuración del terapeuta al mensaje del sistema
    if therapist_style:
        system_message += f"\n\nTu estilo terapéutico es: {therapist_style}"
    if therapist_tone:
        system_message += f"\nTu tono de comunicación debe ser: {therapist_tone}"
    if therapist_instructions:
        system_message += f"\nInstrucciones adicionales: {therapist_instructions}"
    
    # Convertir el historial al formato correcto
    messages = [{"role": "system", "content": system_message}]
    
    if isinstance(chat_history, list):
        for msg in chat_history:
            # Mapear roles: 'user'/'patient' -> 'user', 'assistant'/'psychologist' -> 'assistant'
            original_role = msg.get("role", "user")
            
            if original_role in ["user", "patient"]:
                role = "user"
            elif original_role in ["assistant", "psychologist"]:
                role = "assistant"
            else:
                role = original_role
            
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    
    # Si no hay historial válido, usar fallback
    options = ["¿Cómo te sientes?", "Cuéntame más.", "Te escucho."]
    if len(messages) <= 1:
        print("############# No valid chat history found, returning hardcoded fallbacks.")
        return {
            "options": options[:3],
            "raw_options": [content_model1, content_model2, content_model3]
        }
    
    try:
        content_model1, content_model2, content_model3 = llm_models(messages)
        print(f"LLM Result: Model1={bool(content_model1)}, Model2={bool(content_model2)}, Model3={bool(content_model3)}")
        
        # Procesar y limpiar las respuestas
        options = []
        for content in [content_model1, content_model2, content_model3]:
            if content:
                cleaned = clean_response(content)
                if cleaned and len(cleaned) > 2:
                    options.append(cleaned)
        
        # Fallback si no hay suficientes opciones válidas
        if len(options) < 3:
            print(f"############# Not enough LLM options ({len(options)}), adding fallbacks.")
            fallback_messages = ["¿Cómo te sientes?", "Cuéntame más.", "Te escucho."]
            while len(options) < 3:
                options.append(fallback_messages[len(options)])
        
        return {
            "options": options[:3],
            "raw_options": "Output Model 1: " + str(content_model1) + "\nOutput Model 2: " + str(content_model2) + "\nOutput Model 3: " + str(content_model3)
        }

    except Exception as e:
        print(f"############# Error en generate_response_options final step: {e}")
        return {
            "options": options[:3],
            "raw_options": [content_model1, content_model2, content_model3]
        }
