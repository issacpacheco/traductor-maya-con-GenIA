// src/App.jsx

import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import './App.css';

// URLs de conexión
const FASTAPI_BASE_URL = "ws://localhost:8000/ws/chat/";
const REST_API_URL = "http://localhost:8000/api/sessions/";

function ChatApp() {
    // Generar un ID de cliente único al cargar por primera vez
    const [clientId, setClientId] = useState(`client-${Date.now()}`);
    
    // Mensaje de bienvenida del Profesor Couoh Chi para iniciar la sesión
    const [messages, setMessages] = useState([
        { sender: 'Profesor Couoh Chi', text: '¡Bienvenido al traductor Maya! puedo traducir cualquier frase en cualquier idioma al mayá 🌿' }
    ]);

    const [input, setInput] = useState('');
    const [isConnected, setIsConnected] = useState(false);
    const [isTyping, setIsTyping] = useState(false);

    const ws = useRef(null);
    const chatEndRef = useRef(null);

    // Función para conectar el WebSocket
    const connectWebSocket = () => {
        // Evitar múltiples conexiones
        if (ws.current && (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING)) {
            return;
        }

        const socketUrl = `${FASTAPI_BASE_URL}${clientId}`;
        ws.current = new WebSocket(socketUrl);

        ws.current.onopen = () => {
            console.log('Conexión WebSocket establecida con FastAPI.');
            setIsConnected(true);
        };

        ws.current.onmessage = (event) => {
            const data = JSON.parse(event.data);

            // Usamos la forma funcional y garantizamos la inmutabilidad
            setMessages(prevMessages => {
                const newMessages = [...prevMessages];
                const lastMessageIndex = newMessages.length - 1;
                let lastMessage = newMessages[lastMessageIndex];

                if (data.type === "start") {
                    setIsTyping(true);
                    // Inicia un nuevo mensaje vacío para el nuevo stream
                    // Usamos 'Profesor Couoh Chi' como remitente para el stream de Gemini
                    if (!lastMessage || lastMessage.sender !== 'Profesor Couoh Chi' || lastMessage.text !== '') {
                        return [...prevMessages, { sender: 'Profesor Couoh Chi', text: '' }];
                    }
                    return prevMessages;

                } else if (data.type === "chunk" && data.content) {
                    // Si el último mensaje es de Gemini (Profesor Couoh Chi), agrega el fragmento
                    if (lastMessage && lastMessage.sender === 'Profesor Couoh Chi') {
                        // Creamos una copia inmutable del mensaje anterior para actualizar
                        newMessages[lastMessageIndex] = {
                            ...lastMessage,
                            text: lastMessage.text + data.content
                        };
                        return newMessages;
                    }
                } else if (data.type === "end") {
                    setIsTyping(false);
                } else if (data.error) {
                    setIsTyping(false);
                    // Agrega el error como un mensaje del sistema
                    return [...prevMessages, { sender: 'System', text: `Error: ${data.error}` }];
                }

                // Si ninguna condición de "chunk" se cumplió, devuelve el estado anterior
                return prevMessages;
            });
        };

        ws.current.onclose = () => {
            console.log('Conexión WebSocket cerrada.');
            setIsConnected(false);
            setIsTyping(false);
            // Intentar reconectar después de un breve retraso
            setTimeout(connectWebSocket, 3000);
        };

        ws.current.onerror = (error) => {
            console.error('Error de WebSocket:', error);
            setIsConnected(false);
            // Evitamos llamar a ws.current.close() aquí, ya que onclose manejará la reconexión
        };
    };

    // Efecto para establecer la conexión inicial y la limpieza
    useEffect(() => {
        connectWebSocket();

        // Función de limpieza
        return () => {
            if (ws.current) {
                ws.current.close();
            }
        };
    }, [clientId]);

    // Desplazamiento automático
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, isTyping]);

    // Enviar mensaje
    const sendMessage = (e) => {
        e.preventDefault();
        const textToSend = input.trim();
        if (textToSend === '' || !isConnected || isTyping) return;

        // El usuario es 'Tú'
        const userMessage = { sender: 'Tú', text: textToSend };
        setMessages(prev => [...prev, userMessage]);

        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            // Se envía el texto plano al backend
            ws.current.send(textToSend);
        }

        setInput('');
    };

    // Limpiar historial
    const clearHistory = async () => {
        try {
            const response = await fetch(`${REST_API_URL}${clientId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                // Generar un nuevo client ID para forzar la reconexión y nueva sesión de chat en el backend
                const newClientId = `client-${Date.now()}`;
                
                if (ws.current) {
                    ws.current.close();
                }

                setClientId(newClientId);
                setMessages([]);
                
                // Mensaje de bienvenida del Profesor Couoh Chi después de limpiar
                setMessages([{ sender: 'Profesor Couoh Chi', text: '¡Bienvenido al traductor Maya! puedo traducir cualquier frase en cualquier idioma al mayá 🌿' }]);
                
            } else {
                console.error("Error al borrar historial en el backend.");
                setMessages(prev => [...prev, { sender: 'System', text: 'Error al borrar historial.' }]);
            }

        } catch (error) {
            console.error('Error de red al intentar borrar el historial:', error);
            setMessages(prev => [...prev, { sender: 'System', text: 'Error de conexión.' }]);
        }
    };


    return (
        <div className="chat-container">
            <div className="header-bar">
                <h1 className='title'>Traductor Maya</h1>
                <button
                    onClick={clearHistory}
                    className="clear-button"
                    disabled={!isConnected}
                >
                    Limpiar Historial
                </button>
            </div>

            <p className={`status-bar ${isConnected ? 'connected' : 'disconnected'}`}>
                Estado: {isConnected ? 'Conectado' : 'Desconectado'}
            </p>

            <div className="chat-window">
                {messages.map((msg, index) => (
                    <div
                        key={index}
                        // Usamos 'usuario' para el usuario y 'profesor-couoh-chi' para el asistente
                        className={`message-row ${msg.sender === 'Tú' ? 'usuario' : 'profesor-couoh-chi'}`}
                    >
                        <div className="message-bubble">
                            <strong>{msg.sender}:</strong>

                            {msg.sender === 'Profesor Couoh Chi' ? (
                                <ReactMarkdown>{msg.text}</ReactMarkdown>
                            ) : (
                                msg.text
                            )}
                        </div>
                    </div>
                ))}
                {/* Indicador de que Gemini está escribiendo */}
                {isTyping && (
                    <div className="message-row profesor-couoh-chi">
                        <div className="message-bubble typing-indicator">
                            ... escribiendo ...
                        </div>
                    </div>
                )}
                <div ref={chatEndRef} />
            </div>

            <form onSubmit={sendMessage} className="input-form">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Escribe tu mensaje..."
                    disabled={!isConnected || isTyping}
                />
                <button type="submit" disabled={!isConnected || isTyping}>
                    Enviar
                </button>
            </form>
        </div>
    );
}

export default ChatApp;