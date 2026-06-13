
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { BrowserRouter } from 'react-router-dom'   // ← new import

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>                             {/* ← wrap here */}
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
