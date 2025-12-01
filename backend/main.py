# gemini-chat-backend/main.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from google import genai
from google.genai import types

# --- Módulos de Soporte ---
from dotenv import load_dotenv

# Cargar el archivo .env para acceder a la GEMINI_API_KEY
load_dotenv() 

# --- 1. CONFIGURACIÓN DE FASTAPI ---
app = FastAPI(
    title="Gemini Chat API",
    description="API de backend para el chat en tiempo real con WebSockets.",
)

# Configuración de CORS: Permite la comunicación con el frontend de React.
origins = ["*"] 

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# --- 2. CONEXIÓN Y CONFIGURACIÓN DE GEMINI ---

client = None
file_references = [] # <-- LISTA para almacenar múltiples referencias de archivo

try:
    client = genai.Client()
    print("Cliente de Gemini inicializado correctamente.")
    
    # --- PASO CRÍTICO: Subir los archivos PDF a la API de Gemini ---
    doc_dir = os.path.join(os.path.dirname(__file__), "doc") # Directorio de documentos
    
    # Lista de todos los archivos que queremos subir
    files_to_upload = [
        "Diccionario_Maya_Espanol.pdf",
        "cordemex_diccionario_maya.pdf"
    ]
    
    # Iterar y subir cada archivo
    for file_name in files_to_upload:
        file_path = os.path.join(doc_dir, file_name)
        print(f"Buscando archivo: {file_name}...")
        
        if os.path.exists(file_path):
            print(f"Subiendo archivo: {file_name}...")
            
            # Subir el archivo y obtener el objeto de referencia (sin mime_type)
            ref = client.files.upload(
                file=file_path,
            )
            # Guardar la referencia en la lista
            file_references.append(ref)
            print(f"Archivo subido exitosamente. Nombre de referencia: {ref.name}")
        else:
            print(f"ADVERTENCIA: Archivo '{file_name}' no encontrado. No se adjuntará.")

except Exception as e:
    print(f"Error al inicializar o subir el archivo(s) a Gemini. Revisa tu archivo .env: {e}")

# Diccionario para almacenar las sesiones de chat de Gemini (historial)
chat_sessions = {}

# --- 3. ENDPOINTS REST ---

@app.get("/")
def health_check():
    """Endpoint simple para verificar que la API esté funcionando."""
    return {"status": "ok", "message": "FastAPI y Uvicorn están listos."}

@app.delete("/api/sessions/{client_id}")
def clear_session_history(client_id: str):
    """
    Elimina la sesión de chat de Gemini asociada al client_id (borra el historial).
    """
    if client_id in chat_sessions:
        del chat_sessions[client_id]
        print(f"Historial de chat borrado para el cliente {client_id}.")
        return JSONResponse(status_code=200, content={"message": "Historial borrado exitosamente"})
    else:
        return JSONResponse(status_code=404, content={"message": "Sesión de cliente no encontrada o ya borrada"})


# --- 4. ENDPOINT DE WEBSOCKET (Comunicación en tiempo real) ---

@app.websocket("/ws/chat/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    Maneja la conexión WebSocket para el chat.
    """
    await websocket.accept()
    print(f"Cliente conectado: {client_id}")

    # Inicializar o recuperar la Sesión de Chat de Gemini
    if client_id not in chat_sessions:
        # Check: Asegúrate de que al menos un archivo se haya subido
        if client and file_references: 
            try:
                # 1. DEFINICIÓN DE SYSTEM_INSTRUCTION
                system_instruction = (
                    "Eres un asistente experto en traducción de idiomas, especialmente en el idioma maya. "
                    "Tu tarea es ayudar a los usuarios a traducir frases o palabras de cualquier idioma al maya de manera precisa y culturalmente adecuada. "
                    "Proporciona explicaciones breves sobre las traducciones cuando sea relevante, incluyendo contexto cultural si es necesario. "
                    "Mantén un tono amigable y accesible, adecuado para todos los niveles de conocimiento del idioma maya."
                    "Utiliza la información de TODOS los documentos de referencia adjuntos para mejorar la precisión de las traducciones."
                    "Importante: para la comprensión, contexto y sutilezas culturales del idioma maya, utiliza el documento 'cordemex_diccionario_maya.pdf'."
                    "No solo traduzcas literalmente, sino que también considera el contexto y las sutilezas culturales del idioma maya."
                    "Si no estás seguro de una traducción, indícalo claramente en tu respuesta."
                    
                )
                
                # 2. DEFINICIÓN DE CONFIG (Solo system_instruction y temperatura)
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction, 
                    temperature=0.2, 
                    stop_sequences=[], 
                )
                
                # 3. CREACIÓN DE LA SESIÓN DE CHAT (Sin el argumento 'contents')
                chat_sessions[client_id] = client.chats.create(
                    model="gemini-2.5-flash",
                    config=config
                )

                print(f"Nueva sesión de chat de Gemini iniciada para el cliente {client_id}")
                
                # --- PASO ADICIONAL: ENVIAR ARCHIVOS COMO PRIMER MENSAJE DE CONTEXTO ---
                
                initial_text = (
                    "Por favor, utiliza TODOS los diccionarios adjuntos como principal fuente "
                    "de referencia para todas las peticiones de traducción que se te hagan a partir de ahora."
                )

                # 1. Crear lista de partes
                initial_message_parts = []

                # 2. Convertir cada referencia de archivo a Part
                for ref in file_references:
                    initial_message_parts.append(
                        types.Part(
                            file_data=types.FileData(
                                file_uri=ref.uri,      # ← importante
                                mime_type=ref.mime_type
                            )
                        )
                    )

                # 3. Agregar parte de texto
                initial_message_parts.append(
                    types.Part(text=initial_text)
                )

                # 4. Enviar mensaje inicial al chat
                chat_sessions[client_id].send_message(initial_message_parts)

                print(f"{len(file_references)} Documentos adjuntos al contexto del chat para {client_id}.")

            except Exception as e:
                await websocket.send_json({"error": f"Error al crear sesión con Gemini: {e}"})
                await websocket.close()
                return
        else:
            await websocket.send_json({"error": "El servidor no pudo conectar con Gemini y/o no encontró los diccionarios."})
            await websocket.close()
            return

    chat_session = chat_sessions[client_id]

    try:
        while True:
            # 1. Recibir mensaje del cliente
            data = await websocket.receive_text()
            print(f"Mensaje de {client_id}: {data}")

            # 2. Enviar a Gemini y obtener el stream
            response_stream = chat_session.send_message_stream(data)
            
            # 3. Enviar el stream de respuesta de vuelta al cliente
            
            await websocket.send_json({"type": "start"}) 
            
            full_response = ""
            
            for chunk in response_stream:
                text = chunk.text
                if text:
                    full_response += text 
                    await websocket.send_json({"type": "chunk", "content": text})
            
            await websocket.send_json({"type": "end"}) 
            
            print(f"Respuesta completa enviada a {client_id}.")
            print(f"La respuesta completa generada por Gemini fue:\n--- INICIO DE RESPUESTA ---\n{full_response}\n--- FIN DE RESPUESTA ---")


    except WebSocketDisconnect:
        print(f"Cliente desconectado: {client_id}")
    except Exception as e:
        print(f"Error inesperado en WebSocket con {client_id}: {e}")
        await websocket.send_json({"error": f"Error interno del servidor: {e}"})
        await websocket.close()