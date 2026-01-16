from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_PSICOUJA"),
    base_url=os.getenv("BASE_URL_MODELS_PSICOUJA")
)

def llm_models(messages):
    """
    Llama a los modelos LLM usando OpenAI y devuelve la respuesta.
    
    Args:
        messages (list): Lista de mensajes en formato [{"role": "system/user/assistant", "content": "..."}]
    """
    try:
        response_llama = client.chat.completions.create(
            model=os.getenv("URL_MODELS_PSICOUJA") + "meta-llama/Llama-3.1-8B-Instruct",
            messages=messages,
            max_tokens=256,
            temperature=0.7
        )
        response_gemma = client.chat.completions.create(
            model=os.getenv("URL_MODELS_PSICOUJA") + "google/gemma-3-12b-it",
            messages=messages,
            max_tokens=256,
            temperature=0.7
        )
        response_qwen = client.chat.completions.create(
            model=os.getenv("URL_MODELS_PSICOUJA") + "Qwen/Qwen3-8B",
            messages=messages,
            max_tokens=256,
            temperature=0.7,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        # Extraer contenido y limpiar
        content_llama = response_llama.choices[0].message.content.strip()
        content_gemma = response_gemma.choices[0].message.content.strip()
        content_qwen = response_qwen.choices[0].message.content.strip()
        
        return content_llama, content_gemma, content_qwen
        
    except Exception as e:
        print(f"Error en llm_models: {e}")
        return None, None, None

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
    """
    Genera 3 opciones de respuesta para el psicólogo basadas en el historial del chat.
    
    Args:
        chat_history (list): Lista de diccionarios [{'role': 'user'/'assistant', 'content': '...'}, ...]
        therapist_style (str, optional): Estilo terapéutico del psicólogo.
        therapist_tone (str, optional): Tono de comunicación preferido.
        therapist_instructions (str, optional): Instrucciones adicionales del terapeuta.
    
    Returns:
        list: Lista con 3 opciones de respuesta (strings).
    """
    
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
            if content:  # Solo agregar si hay contenido
                messages.append({"role": role, "content": content})
    
    # Si no hay historial válido, usar fallback
    if len(messages) <= 1:
        return [
            "Hola, es un gusto conocerte. ¿Qué te trae por aquí hoy?",
            "Bienvenido/a. Cuéntame, ¿en qué puedo ayudarte?",
            "Hola. Este es un espacio seguro para ti. ¿Qué te gustaría compartir hoy?"
        ]
    
    try:
        # Llamar a los modelos con el historial formateado
        content_llama, content_gemma, content_qwen = llm_models(messages)
        print("......")
        print(content_llama, content_gemma, content_qwen)
        
        # Procesar y limpiar las respuestas
        options = []
        
        for content in [content_llama, content_gemma, content_qwen]:
            if content:
                cleaned = clean_response(content)
                if cleaned and len(cleaned) > 10:  # Validar que tenga contenido útil
                    options.append(cleaned)
        
        # Fallback si no hay suficientes opciones válidas
        if len(options) < 3:
            fallback_messages = [
                "Entiendo lo que compartes. ¿Podrías contarme más sobre cómo te sientes?",
                "Es importante que expreses tus emociones. ¿Qué ha sido lo más difícil para ti?",
                "Gracias por compartir esto conmigo. ¿Cómo has estado manejando esta situación?"
            ]
            while len(options) < 3:
                options.append(fallback_messages[len(options)])
        
        return options[:3]

    except Exception as e:
        print(f"Error generando opciones: {e}")
        return [
            "Entiendo. ¿Puedes contarme más sobre eso?",
            "Gracias por compartir. ¿Cómo te hace sentir esta situación?",
            "Veo que esto es importante para ti. ¿Qué te gustaría trabajar al respecto?"
        ]