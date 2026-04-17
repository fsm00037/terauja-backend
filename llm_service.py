from openai import AsyncOpenAI
from dotenv import load_dotenv
import logging
import os
import asyncio
import tiktoken

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "llm_activity.log")

from utils.logger import logger

# Agregar handler de actividad LLM al logger centralizado
llm_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
llm_handler.setLevel(logging.INFO)
llm_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
llm_handler.setFormatter(llm_formatter)
logger.addHandler(llm_handler)

load_dotenv()

# Async client
client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY_PSICOUJA"),
    base_url=os.getenv("BASE_URL_MODELS_PSICOUJA")
)

# Límite de tokens para el contexto
MAX_TOKENS = 8192
# Reservar tokens para la respuesta del modelo
RESERVED_TOKENS = 256

def count_tokens(messages, model="gpt-3.5-turbo"):
    """
    Cuenta los tokens en una lista de mensajes.
    Usa tiktoken para estimar los tokens de forma precisa.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    
    num_tokens = 0
    for message in messages:
        num_tokens += 4
        for key, value in message.items():
            num_tokens += len(encoding.encode(str(value)))
    
    num_tokens += 2
    return num_tokens

def truncate_messages(messages, max_tokens=MAX_TOKENS - RESERVED_TOKENS):
    """
    Trunca el historial de mensajes eliminando los más antiguos hasta que
    el total de tokens esté por debajo del límite.
    """
    if not messages:
        return messages
    
    current_tokens = count_tokens(messages)
    
    if current_tokens <= max_tokens:
        # Se ha reducido el ruido de este log ya que es informativo pero frecuente
        # logger.debug(f"Messages within token limit: {current_tokens}/{max_tokens} tokens")
        return messages
    
    logger.warning(f"Messages exceed token limit: {current_tokens}/{max_tokens} tokens. Truncating...")
    
    system_message = messages[0] if messages[0].get("role") == "system" else None
    conversation_messages = messages[1:] if system_message else messages[:]
    
    if not conversation_messages:
        return messages
    
    truncated = [system_message] if system_message else []
    
    for i in range(len(conversation_messages) - 1, -1, -1):
        test_messages = [system_message] if system_message else []
        test_messages.extend(conversation_messages[i:])
        
        tokens = count_tokens(test_messages)
        
        if tokens <= max_tokens:
            truncated = test_messages
        else:
            break
    
    messages_removed = len(messages) - len(truncated)
    if messages_removed > 0:
        logger.info(f"Removed {messages_removed} old messages. New token count: {count_tokens(truncated)}")
    
    return truncated

def clean_messages(messages):
    """
    Normaliza la lista de mensajes combinando roles consecutivos repetidos.
    """
    if not messages:
        return []
    
    cleaned = []
    for msg in messages:
        if cleaned and cleaned[-1]['role'] == msg['role']:
            cleaned[-1]['content'] += f" {msg['content']}"
        else:
            cleaned.append(dict(msg))
    return cleaned


async def _call_llama(messages):
    """Llama al modelo Llama de forma asíncrona."""
    url_prefix = os.getenv("URL_MODELS_PSICOUJA", "")
    try:
        logger.info("Calling Llama model...")
        response = await client.chat.completions.create(
            model=url_prefix + "meta-llama/Llama-3.1-8B-Instruct",
            messages=messages,
            max_tokens=256,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        logger.info("Llama call successful.")
        return content
    except Exception as ex:
        logger.error(f"Error calling Llama: {ex}")
        return str(ex)


async def _call_qwen(messages):
    """Llama al modelo Qwen de forma asíncrona."""
    url_prefix = os.getenv("URL_MODELS_PSICOUJA", "")
    try:
        logger.info("Calling Qwen model...")
        response = await client.chat.completions.create(
            model="Qwen3.5-9B",
            messages=messages,
            max_tokens=256,
            temperature=0.7,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = response.choices[0].message.content.strip()
        logger.info("Qwen call successful.")
        return content
    except Exception as ex:
        logger.error(f"Error calling Qwen: {ex}")
        return str(ex)


async def _call_gemma(messages):
    """Llama al modelo Gemma de forma asíncrona (requiere ajuste del rol system)."""
    url_prefix = os.getenv("URL_MODELS_PSICOUJA", "")
    # Gemma no soporta role 'system', se convierte a 'user'
    gemma_messages = []
    for msg in messages:
        if msg["role"] == "system":
            gemma_messages.append({"role": "user", "content": msg["content"]})
        else:
            gemma_messages.append(dict(msg))
    gemma_messages = clean_messages(gemma_messages)

    try:
        logger.info("Calling Gemma model...")
        response = await client.chat.completions.create(
            model="gemma-4-E4B-it",
            messages=gemma_messages,
            max_tokens=256,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        logger.info("Gemma call successful.")
        return content
    except Exception as ex:
        logger.error(f"Error calling Gemma: {ex}")
        return str(ex)


def clean_response(text):
    """
    Limpia la respuesta del modelo eliminando prefijos comunes y texto no deseado.
    """
    if "Error code:" in text:
        return ""
    if not text:
        return ""
    
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


def _build_messages(chat_history, therapist_style=None, therapist_tone=None, therapist_instructions=None):
    """
    Construye la lista de mensajes formateada para los modelos a partir del historial.
    Devuelve None si el historial no es válido.
    """
    system_message = """Eres un psicólogo profesional en una sesión terapéutica. Estás conversando con un paciente y debes continuar la conversación siempre con rol de psicólogo. No digas nada fuera de lugar.\nIMPORTANTE:\n- Responde SOLO con lo que dirías al paciente como terapeuta, sin explicaciones adicionales\n- NO incluyas prefijos como "Psicólogo:", "Respuesta:" o similares"""
    
    if therapist_style:
        if therapist_style.lower() == "act":
            system_message += """\n\nActúa como un terapeuta experto en Terapia de Aceptación y Compromiso (ACT). Tu objetivo es ayudar al usuario a desarrollar flexibilidad psicológica siguiendo los principios de esta corriente.

### TUS PRINCIPIOS FUNDAMENTALES:
1. **No "arreglas" personas:** No veas los síntomas (ansiedad, dolor, tristeza) como algo que debe ser eliminado para que la persona sea feliz. El objetivo no es el alivio inmediato, sino la conexión con una vida valiosa.
2. **Aceptación vs. Lucha:** Enseña que luchar contra los pensamientos/emociones es paradójico (genera más malestar a largo plazo). Tu labor es ayudar a "soltar la cuerda" en la lucha contra el malestar.
3. **Foco en la Utilidad, no en la Verdad:** Si el usuario dice "Soy un inútil", no debatas si es verdad o mentira. Pregunta: "¿Hacerle caso a ese pensamiento te ayuda a ser la persona que quieres ser?" o "¿Qué sucede cuando te quedas enganchado a esa idea?".
4. **Acción comprometida:** Motiva al usuario a dar pasos pequeños hacia sus valores, incluso si el malestar (el "dolor", la "culpa") está presente.

### TU ESTILO DE COMUNICACIÓN:
* **Actitud:** Curiosa, compasiva, horizontal y no juiciosa. Usa la validación ("Es normal que te sientas así dada tu historia").
* **Herramientas:** Usa metáforas, ejercicios prácticos y ejemplos de la vida cotidiana.
* **El "Yo Observador":** Ayuda al usuario a distanciarse de sus pensamientos (Defusión Cognitiva). Trata los pensamientos como palabras o eventos que pasan, no como verdades absolutas.
* **Lenguaje:** Evita tecnicismos innecesarios. Sé cercano.

### ESTRUCTURA DE TUS INTERVENCIONES:
1. **Validar:** Reconoce el dolor o la dificultad del usuario.
2. **Cuestionar la Evitación:** Hazle notar si lo que está haciendo para no sufrir lo está alejando de sus valores o de su vida (ej. "¿Esa estrategia de quedarte en casa te está funcionando a largo plazo?").
3. **Proponer un cambio de perspectiva:** Introduce una metáfora o un ejercicio de observación para ver el problema desde fuera.
4. **Mover a la acción:** Finaliza preguntando por un paso pequeño y concreto que el usuario pueda dar hoy, coherente con sus valores, "llevándose el malestar al hombro" si es necesario.

### INSTRUCCIÓN ESPECIAL:
Si el usuario se queda atrapado en el "por qué" de su dolor, redirígelo suavemente hacia el "para qué" de sus acciones y hacia lo que sí puede controlar: su conducta presente."""
        elif therapist_style.lower() in ("ctt", "cbt"):
            system_message += """\n\nActúa como un terapeuta experto en Terapia Cognitivo-Conductual (TCC/CBT). Tu objetivo es ayudar al usuario a identificar y modificar patrones de pensamiento disfuncionales y conductas de evitación que mantienen su malestar, facilitando un aprendizaje correctivo duradero.

### TUS PRINCIPIOS FUNDAMENTALES:
1. **El modelo cognitivo como brújula:** Los pensamientos, emociones y conductas están interconectados. Tu labor es ayudar al usuario a detectar cómo sus interpretaciones (no los hechos en sí) generan el malestar y lo perpetúan.
2. **Colaboración empírica:** Eres un "detective colaborativo", no un experto que dicta verdades. Junto al usuario, examináis las creencias como hipótesis a contrastar, no como certezas ni mentiras. La pregunta clave es: "¿Qué evidencias tenemos a favor y en contra de esa idea?"
3. **La evitación es el enemigo silencioso:** Enseña que evitar lo que genera ansiedad produce alivio inmediato pero alimenta el problema a largo plazo. La exposición gradual y controlada al malestar es el camino hacia la recuperación real.
4. **Acción como generadora de cambio:** El cambio conductual no espera a que "uno se sienta listo". Actuar de forma diferente —aunque con ansiedad— genera nuevas evidencias que modifican las creencias disfuncionales.

### TU ESTILO DE COMUNICACIÓN:
* **Actitud:** Socrática, empática, estructurada y orientada a objetivos concretos. Usa el cuestionamiento guiado, nunca la confrontación directa ("¿Qué te llevaría a pensar eso?", "¿Hay otra forma de interpretar esta situación?").
* **Herramientas:** Utiliza registros de pensamientos, experimentos conductuales, psicoeducación clara y ejemplos cotidianos. Cuando sea útil, usa metáforas ("el pensamiento como alarma de humo", "la evitación como bola de nieve").
* **Distancia del pensamiento:** Ayuda al usuario a ver sus pensamientos automáticos como hipótesis, no como hechos ("Tienes el pensamiento de que... ¿qué tan cierto es eso al 100%?").
* **Lenguaje:** Directo pero cálido, sin jerga clínica innecesaria. Psicoeducativo cuando aporta valor.

### ESTRUCTURA DE TUS INTERVENCIONES:
1. **Validar y normalizar:** Reconoce el malestar del usuario y encuádralo dentro del modelo TCC sin patologizar ("Es comprensible que tu mente haga eso; es lo que los pensamientos automáticos hacen bajo estrés").
2. **Identificar el patrón:** Ayuda a detectar el pensamiento automático, la emoción asociada y la conducta resultante. Usa la secuencia A-B-C si es útil: Situación → Pensamiento → Emoción → Conducta.
3. **Cuestionar la evidencia:** Aplica el diálogo socrático. Pregunta por evidencias a favor, en contra, qué diría un amigo objetivo, qué probabilidad real tiene la catástrofe temida, y cuál sería el peor/mejor/más probable escenario.
4. **Proponer un experimento o tarea:** Diseña con el usuario un pequeño experimento conductual o una tarea de exposición gradual que permita contrastar la creencia con la realidad ("¿Qué pasaría si probases hacer X esta semana?").

### HERRAMIENTAS ESPECÍFICAS QUE PUEDES USAR:
- **Registro de pensamientos:** Guía al usuario a completar mentalmente: situación → pensamiento automático → emoción (0-100) → distorsión probable → pensamiento alternativo → emoción tras el cambio (0-100).
- **Escala de USAs:** Usa Unidades Subjetivas de Ansiedad (0-100) para medir y hacer seguimiento del malestar de forma concreta.
- **Flecha descendente:** Si el pensamiento es superficial, profundiza con "Y si eso fuera cierto... ¿qué significaría para ti?" hasta llegar al miedo nuclear.
- **Jerarquía de exposición:** Si hay evitación, construye junto al usuario una lista de situaciones temidas de menor a mayor dificultad, y motívalo a comenzar por los escalones más bajos.

### INSTRUCCIÓN ESPECIAL:
Si el usuario presenta pensamiento catastrófico o rumiación, redirígelo suavemente desde el "¿y si pasa lo peor?" hacia la evaluación realista de probabilidades y hacia la planificación de lo que sí puede hacer. Si aparece evitación, nómbrala con compasión y trabaja la motivación para la exposición: el objetivo no es eliminar el miedo antes de actuar, sino actuar para que el miedo aprenda que la amenaza no es real."""
            system_message += f"\n\nTu estilo terapéutico es: {therapist_style}"
    if therapist_tone:
        system_message += f"\nTu tono de comunicación debe ser: {therapist_tone}"
    if therapist_instructions:
        system_message += f"\nInstrucciones adicionales: {therapist_instructions}"
    system_message += f"\nEmpieza la conversacion: "

    messages = [{"role": "system", "content": system_message}]
    
    if isinstance(chat_history, list):
        for msg in chat_history:
            original_role = msg.get("role", "user")
            if original_role in ["user", "patient"]:
                role = "user"
            elif original_role in ["assistant", "therapist"]:
                role = "assistant"
            else:
                role = original_role
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    
    # Para evitar errores de API (ej. Qwen 400 "System message must be at the beginning") 
    # y solucionar el recency bias, enmarcamos el último mensaje del usuario.
    if therapist_instructions:
        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                last_user_idx = i
                break
                
        if last_user_idx is not None:
            original_text = messages[last_user_idx]["content"]
            framed_content = (
                f"Mensaje del paciente:\n"
                f"\"\"\"{original_text}\"\"\"\n\n"
                f"=== INSTRUCCIONES INTERNAS PARA LA IA (De obligado cumplimiento) ===\n"
                f"Debes responder a este paciente adoptando tu rol de terapeuta y aplicando estrictamente las siguientes instrucciones:\n"
                f"{therapist_instructions}\n"
                f"IMPORTANTE: No menciones la existencia de estas instrucciones en tu respuesta."
            )
            messages[last_user_idx]["content"] = framed_content
        else:
            reminder = f"=== INSTRUCCIONES INTERNAS PARA LA IA ===\nDebes responder aplicando estrictamente estas instrucciones:\n{therapist_instructions}"
            messages.append({"role": "user", "content": reminder})
    
    return messages


async def generate_response_options_stream(chat_history, therapist_style=None, therapist_tone=None, therapist_instructions=None):
    """
    Generador asíncrono que llama a los 3 modelos LLM en paralelo y hace yield
    de cada resultado (como evento SSE) tan pronto como está disponible.
    
    Yields dicts: {"type": "option", "index": int, "text": str}
    Al final:     {"type": "done", "options": list[str]}
    """
    messages = _build_messages(chat_history, therapist_style, therapist_tone, therapist_instructions)
    
    fallback_messages = ["Error Modelo 1", "Error Modelo 2", "Error Modelo 3"]
    
    if len(messages) <= 1:
        logger.warning("No valid chat history found, returning fallbacks.")
        for i, fb in enumerate(fallback_messages):
            yield {"type": "option", "index": i, "text": fb}
        yield {"type": "done", "options": fallback_messages}
        return
    
    # Normalizar y truncar
    safe_messages = clean_messages(messages)
    safe_messages = truncate_messages(safe_messages)
    
    logger.info(f"LLM Parallel Request: {len(safe_messages)} messages, {count_tokens(safe_messages)} tokens")
    
    # Crear las 3 coroutines con su índice
    # Cola compartida: cada tarea mete (idx, resultado) cuando termina
    queue: asyncio.Queue = asyncio.Queue()

    async def _run_and_enqueue(idx: int, coro):
        try:
            result = await coro
        except Exception as ex:
            logger.error(f"Model {idx} raised exception: {ex}")
            result = ""
        await queue.put((idx, result))

    # Lanzar las 3 tareas en paralelo
    tasks = [
        asyncio.create_task(_run_and_enqueue(0, _call_llama(safe_messages))),
        asyncio.create_task(_run_and_enqueue(1, _call_qwen(safe_messages))),
        asyncio.create_task(_run_and_enqueue(2, _call_gemma(safe_messages))),
    ]

    raw_results = {}

    # Recoger resultados en el orden en que llegan
    for _ in range(3):
        idx, raw_content = await queue.get()
        cleaned = clean_response(raw_content) if raw_content else ""
        raw_results[idx] = cleaned
        logger.info(f"Model {idx} completed. Streaming option...")
        yield {"type": "option", "index": idx, "text": cleaned}

    # Aseguramos que todas las tareas hayan terminado antes de continuar
    await asyncio.gather(*tasks, return_exceptions=True)

    # Construir lista final ordenada (índices 0, 1, 2)
    final_options = [raw_results.get(i, "") for i in range(3)]
    # Rellenar fallbacks si alguno quedó vacío
    for i, opt in enumerate(final_options):
        if not opt or len(opt) < 3:
            final_options[i] = fallback_messages[i]

    logger.info("--- PARALLEL LLM calls completed ---")
    yield {"type": "done", "options": final_options}


async def generate_response_options(chat_history, therapist_style=None, therapist_tone=None, therapist_instructions=None):
    """
    Versión no-streaming para compatibilidad. Llama a los 3 modelos en paralelo
    con asyncio.gather y retorna el resultado cuando todos han terminado.
    """
    messages = _build_messages(chat_history, therapist_style, therapist_tone, therapist_instructions)
    
    fallback_messages = ["Error Modelo 1", "Error Modelo 2", "Error Modelo 3"]
    
    if len(messages) <= 1:
        logger.warning("No valid chat history found, returning hardcoded fallbacks.")
        return {
            "options": fallback_messages,
            "raw_options": ""
        }
    
    safe_messages = clean_messages(messages)
    safe_messages = truncate_messages(safe_messages)
    
    logger.info(f"--- Starting PARALLEL LLM calls ({len(safe_messages)} messages, {count_tokens(safe_messages)} tokens) ---")
    
    try:
        # Llamadas paralelas con asyncio.gather
        content_model1, content_model2, content_model3 = await asyncio.gather(
            _call_llama(safe_messages),
            _call_qwen(safe_messages),
            _call_gemma(safe_messages),
            return_exceptions=True
        )
        
        # Si alguno lanzó excepción, convertirlo en string
        raw_results = []
        for r in [content_model1, content_model2, content_model3]:
            if isinstance(r, Exception):
                raw_results.append(str(r))
            else:
                raw_results.append(r or "")
        
        options = []
        for content in raw_results:
            cleaned = clean_response(content)
            if cleaned and len(cleaned) > 2:
                options.append(cleaned)
        
        if len(options) < 3:
            logger.warning(f"Not enough LLM options ({len(options)}), adding fallbacks.")
            while len(options) < 3:
                options.append(fallback_messages[len(options)])
        
        logger.info("--- PARALLEL LLM calls completed ---")
        return {
            "options": options,
            "raw_options": "Output Model 1: " + str(raw_results[0]) + "\nOutput Model 2: " + str(raw_results[1]) + "\nOutput Model 3: " + str(raw_results[2])
        }

    except Exception as e:
        logger.error(f"Error in generate_response_options: {e}")
        return {
            "options": fallback_messages,
            "raw_options": str(e)
        }

async def generate_strategy_options(chat_history):
    """
    Generate quick strategic instruction pills using Gemma based on the conversation history.
    """
    system_instruction = (
        "Analiza el historial de esta conversación terapéutica. "
        "Como experto supervisor clínico, proporciona EXACTAMENTE 4 opciones de estrategias o instrucciones MUY BREVES (máximo 15 palabras cada una) "
        "que el psicólogo podría intentar en su siguiente respuesta.\n"
        "Las opciones deben ser variadas (ej. validar emociones, explorar pensamientos, confrontar amablemente, encuadrar).\n"
        "RESPONDE ÚNICAMENTE con una lista de viñetas, usando el símbolo '-'. "
        "NO incluyas introducciones, bienvenidas, ni despedidas. Ejemplo:\n"
        "- Validar la frustración del paciente ante la sobrecarga laboral.\n"
        "- Explorar qué pensamientos automáticos preceden a su ansiedad.\n"
        "- Resumir los puntos clave y preparar el cierre de la sesión.\n"
        "- Enfocar la atención en sus logros de esta semana."
    )

    # Re-use _build_messages logic but ignore therapist style/tone to get pure context
    messages = []
    messages.append({"role": "system", "content": system_instruction})
    
    if isinstance(chat_history, list):
        for msg in chat_history:
            original_role = msg.get("role", "user")
            # Map roles properly
            role = "user" if original_role in ["user", "patient"] else "assistant"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
                
    # To force Gemma to output the strategies, we append a final instruction message in user role
    # because Gemma handles instructions better in the user role.
    messages.append({
        "role": "user", 
        "content": "A partir de lo anterior, genera la lista de viñetas con las 4 estrategias. SOLO LA LISTA, NUNCA DES EXPLICACIONES."
    })
    
    safe_messages = clean_messages(messages)
    safe_messages = truncate_messages(safe_messages)
    
    logger.info(f"Generating strategies with Gemma... ({count_tokens(safe_messages)} tokens)")
    try:
        raw_output = await _call_gemma(safe_messages)
        # Parse bullet points
        strategies = []
        for line in raw_output.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                # Remove the bullet
                strategy = line[2:].strip()
                if strategy:
                    strategies.append(strategy)
        
        # Fallback if parsing failed
        if not strategies:
            logger.warning(f"Failed to parse strategies from Gemma output. Raw: {raw_output}")
            strategies = [
                "👋 Saluda de forma cálida al paciente.",
                "🔍 Haz preguntas abiertas para explorar.",
                "🤝 Valida las emociones del paciente.",
                "🛑 Resume lo hablado para el cierre."
            ]
            
        return strategies[:4] # ensure max 4
    except Exception as e:
        logger.error(f"Error in generate_strategy_options: {e}")
        return [
            "👋 Saluda de forma cálida al paciente.",
            "🔍 Haz preguntas abiertas para explorar.",
            "🤝 Valida las emociones del paciente.",
            "🛑 Resume lo hablado para el cierre."
        ]


async def generate_ia_patient_response(chat_history, patient_personality_prompt=None):
    """
    Generate a response as a fictional patient using Gemma.
    The roles are inverted: therapist messages become 'user' and patient messages become 'assistant',
    so Gemma generates the next 'patient' utterance.
    """
    default_personality = (
        "Eres María, una paciente ficticia de 28 años con ansiedad generalizada. "
        "Trabajas como diseñadora gráfica freelance. Tienes dificultades para dormir, "
        "pensamientos catastrofistas recurrentes y tiendes a evitar situaciones sociales. "
        "Eres inteligente y reflexiva pero te cuesta poner en práctica los consejos. "
        "Hablas de forma natural, a veces con dudas, y puedes mostrar resistencia al cambio. "
        "No seas demasiado complaciente: muestra emociones reales, frustraciones y a veces desacuerdo."
    )

    personality = patient_personality_prompt.strip() if patient_personality_prompt and patient_personality_prompt.strip() else default_personality

    system_message = (
        f"Estas en una sesion de chat por mensajes de texto de terapia en una plataforma online con un psicologo."
        f"Debes ser sincero y natural\n\n"
        f"Tu personalidad:\n{personality}\n\n"
        f"INSTRUCCIONES:\n"
        f"- Responde SOLO como paciente, en primera persona.\n"
        f"- NO escribas pensamientos,acotaciones,ni nada que no sea lo que quieres escribir\n"
        f"- Sé natural y realista. Puedes ser breve o extenso según el contexto. teniendo en cuenta que usarás un chat por mensajes de texto.\n"
        f"- Si el terapeuta te saluda, responde con naturalidad.\n"
        f"- NO uses prefijos como 'Paciente:' ni 'Respuesta:'.\n"
        f"- Responde en español."
    )

    # Build messages with INVERTED roles:
    # Therapist (assistant in original) -> user (so Gemma sees therapist as the one talking TO the patient)
    # Patient (user in original) -> assistant (so Gemma continues as the patient)
    messages = [{"role": "system", "content": system_message}]

    if isinstance(chat_history, list):
        for msg in chat_history:
            original_role = msg.get("role", "user")
            # In the original chat: user=patient, assistant=therapist
            # We invert: therapist messages -> user, patient messages -> assistant
            if original_role in ["assistant", "therapist"]:
                role = "user"  # Therapist talking to patient -> Gemma sees as input
            elif original_role in ["user", "patient"]:
                role = "assistant"  # Patient responses -> Gemma continues as patient
            else:
                role = original_role
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

    safe_messages = clean_messages(messages)
    safe_messages = truncate_messages(safe_messages)

    logger.info(f"Generating IA patient response with Gemma ({count_tokens(safe_messages)} tokens)")

    try:
        raw_output = await _call_gemma(safe_messages)
        cleaned = clean_response(raw_output) if raw_output else ""

        if not cleaned or len(cleaned) < 3:
            cleaned = "No sé qué decir ahora mismo... necesito un momento para pensar."

        logger.info(f"IA Patient response generated: {cleaned[:100]}...")
        return cleaned
    except Exception as e:
        logger.error(f"Error in generate_ia_patient_response: {e}")
        return "Perdona, me he quedado en blanco... ¿puedes repetir?"
