from openai import OpenAI
from dotenv import load_dotenv

import os

load_dotenv()


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_PSICOUJA"),  # tu API Key
    base_url="http://ada01.ujaen.es:8080/v1"
)



def mi_modelo(input_text, context=None):
    """
    Llama a tu modelo GPT usando OpenAI y devuelve la respuesta.
    """
    prompt = input_text
    if context:
        prompt = f"{context}\n{input_text}"

    response = client.chat.completions.create(
        model="/mnt/beegfs/sinai-data/google/gemma-3-12b-it",  # Reemplaza con el nombre del modelo en tu servidor
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256
    )
    return response.choices[0].message.content

def generate_response_options(chat_history, therapist_style=None, therapist_tone=None, therapist_instructions=None):
    """
    Genera 3 opciones de respuesta para el psicólogo basadas en el historial del chat.
    
    Args:
        chat_history (list): Lista de diccionarios [{'role': 'user'/'assistant', 'content': '...'}, ...]
                             o una cadena de texto con el historial.
        therapist_style (str, optional): Estilo terapéutico del psicólogo.
        therapist_tone (str, optional): Tono de comunicación preferido.
        therapist_instructions (str, optional): Instrucciones adicionales del terapeuta.
    
    Returns:
        list: Lista con 3 opciones de respuesta (strings).
    """
    
    # Construir el contexto base para el prompt
    contexto = "Eres un asistente de IA para psicólogos. Tu tarea es analizar el historial de conversación con un paciente y sugerir 3 opciones de respuesta posibles para el psicólogo. Las opciones deben ser:\\n1. Empática y validante.\\n2. Indagatoria (haciendo una pregunta relevante).\\n3. Orientada a la acción o psicoeducativa.\\n\\nDevuelve SOLAMENTE las 3 opciones numeradas (1., 2., 3.) sin texto introductorio ni explicaciones adicionales."
    
    # Añadir configuración del terapeuta si está disponible
    if therapist_style:
        contexto += f"\\n\\nEstilo terapéutico: {therapist_style}"
    if therapist_tone:
        contexto += f"\\nTono de comunicación: {therapist_tone}"
    if therapist_instructions:
        contexto += f"\\nInstrucciones adicionales: {therapist_instructions}"
    
    # Formatear el historial si es una lista de objetos
    historial_str = ""
    if isinstance(chat_history, list):
        for msg in chat_history:
            # Asumimos que 'role' puede ser 'patient'/'user' o 'psychologist'/'assistant'
            role = "Paciente" if msg.get("role") in ["user", "patient"] else "Psicólogo"
            content = msg.get("content", "")
            historial_str += f"{role}: {content}\n"
    elif isinstance(chat_history, str):
        historial_str = chat_history

    prompt = f"{contexto}\n\nHistorial de Chat:\n{historial_str}\n\nOpciones de respuesta:"
    print(prompt)
    try:
        response = client.chat.completions.create(
            model="/mnt/beegfs/sinai-data/google/gemma-3-12b-it",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.7 
        )
        content = response.choices[0].message.content
        
        # Procesar la respuesta para extraer las líneas
        options = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if line and (line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or line.startswith('-')):
                # Limpiar la numeración inicial
                clean_line = line.split('.', 1)[-1].strip() if '.' in line[:3] else line
                clean_line = clean_line.split('-', 1)[-1].strip() if line.startswith('-') else clean_line
                options.append(clean_line)
        
        # Fallback simple si el parseo falla pero hay contenido
        if not options and content:
             options = [content]

        return options[:3] # Asegurar máximo 3

    except Exception as e:
        print(f"Error generando opciones: {e}")
        return ["Error generando opciones.", "Por favor intente de nuevo.", "Verifique la conexión."]

