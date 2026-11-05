import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import { BrowserRouter, createBrowserRouter, RouterProvider } from 'react-router-dom';
import WebsiteRenderFailure, { WebsiteMounted } from './auth/WebsiteRenderFailure';

// Website navigation blocking requires a data router; Electron keeps its wrapper.
const isAdminPath = () => window.location.pathname.toLowerCase().startsWith('/auth/admin/')
const websiteRouter = window.electronAPI ? null : createBrowserRouter([{
  path: '/auth/admin/*',
  element: <App />,
}, {
  path: '*',
  element: <App />,
  errorElement: <WebsiteRenderFailure />
}]);
const root = ReactDOM.createRoot(document.getElementById('root'), websiteRouter && !isAdminPath()
  ? { onCaughtError() { /* Customer render errors may contain private values. */ } } : undefined);
// Vite dispatches this for failed lazy chunks. Unmount the old page safely;
// there is no automatic reload or repeat of the failed operation.
if (websiteRouter) window.addEventListener('vite:preloadError', event => {
  if (isAdminPath()) return;
  event.preventDefault();
  root.render(<WebsiteRenderFailure />);
});
root.render(<React.StrictMode>
    {websiteRouter ? <WebsiteMounted><RouterProvider router={websiteRouter} onError={() => { /* Do not log payloads, auth URLs or user content. */ }} /></WebsiteMounted> : <BrowserRouter><App /></BrowserRouter>}
  </React.StrictMode>);
