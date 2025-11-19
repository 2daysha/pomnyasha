import React, { useState, useRef, useEffect } from 'react';
import './ChatPage.css';

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

const ChatPage = ({ onBack }) => {
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Привет! Я Помняша, ИИ-ассистент для планирования.\nПиши свои задачи — помогу всё разложить по времени!",
      isUser: false,
      timestamp: new Date()
    }
  ]);

  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessageToAPI = async (text) => {
    const response = await fetch(`${API_URL}/chat`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text })
    });

    const data = await response.json();
    return data.reply;
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || isLoading) return;

    const userMsg = {
      id: Date.now(),
      text: inputMessage,
      isUser: true,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const botText = await sendMessageToAPI(inputMessage);

      const botMsg = {
        id: Date.now() + 1,
        text: botText,
        isUser: false,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, botMsg]);
    } catch (error) {
      const errMsg = {
        id: Date.now() + 1,
        text: "⚠ Ошибка соединения с сервером.",
        isUser: false,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  return (
    <div className="chat-page">
      <header className="chat-header">
        <button className="back-button" onClick={onBack}>← Назад</button>
        <h1>Чат с Помняшей</h1>
      </header>

      <div className="chat-messages">
        {messages.map(m => (
          <div key={m.id} className={`message ${m.isUser ? 'user-message' : 'bot-message'}`}>
            <div className="message-content">
              {m.text.split('\n').map((line, i) => <p key={i}>{line}</p>)}
            </div>
            <span className="message-time">
              {m.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}

        {isLoading && (
          <div className="message bot-message">
            <div className="message-content loading">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-form" onSubmit={handleSendMessage}>
        <div className="input-container">
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Введите сообщение..."
            onKeyPress={handleKeyPress}
            disabled={isLoading}
          />
          <button type="submit" disabled={!inputMessage.trim() || isLoading}>
            {isLoading ? "⏳" : "📨"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ChatPage;