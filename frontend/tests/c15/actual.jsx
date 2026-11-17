import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthLoginPage, AuthSettingsPage } from '../../src/auth/AuthScreens'
import { PrivacyStatus } from '../../src/auth/WebsiteSettings'
import '../../src/index.css'
createRoot(document.getElementById('root')).render(<BrowserRouter><Routes>
<Route path="/auth/login" element={<AuthLoginPage backendUrl="" />} />
<Route path="/auth/privacy-status" element={<PrivacyStatus />} />
<Route path="*" element={<AuthSettingsPage backendUrl="" />} />
</Routes></BrowserRouter>)
