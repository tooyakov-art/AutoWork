import { useState } from 'react'
import './App.css'

function App() {
  const [count, setCount] = useState(0)
  const [emoji, setEmoji] = useState('👋')

  const emojis = ['👋', '🚀', '🔥', '💡', '⚡', '🎯', '✅', '🎉']

  const randomEmoji = () => {
    const next = emojis[Math.floor(Math.random() * emojis.length)]
    setEmoji(next)
  }

  return (
    <div className="app">
      <div className="hero">
        <span className="big-emoji" onClick={randomEmoji}>{emoji}</span>
        <h1>AutoWork</h1>
        <p className="subtitle">Тестовый сайт — деплой через телефон</p>
      </div>

      <div className="card">
        <button onClick={() => setCount(c => c + 1)}>
          Нажато: {count} раз
        </button>
      </div>

      <div className="info">
        <p>React + Vite + GitHub Pages</p>
        <p className="hint">Нажми на эмодзи сверху</p>
      </div>
    </div>
  )
}

export default App
