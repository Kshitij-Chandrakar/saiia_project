import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import { BrowserRouter, createBrowserRouter, RouterProvider } from 'react-router-dom';
import WebsiteRenderFailure, { WebsiteMounted } from './auth/WebsiteRenderFailure';
import SubscriptionAdmin from './auth/SubscriptionAdmin';
import BillingAdmin from './auth/BillingAdmin';

const isAdminPath = () => window.location.pathname.toLowerCase().startsWith('/auth/admin/')
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'
const reportRouterError = (error, { location } = {}) => {
  if (location?.pathname.toLowerCase().startsWith('/auth/admin/')) console.error(error)
}
const websiteRouter = window.electronAPI ? null : createBrowserRouter([{
  path: '/auth/admin/subscriptions',
  element: <SubscriptionAdmin backendUrl={BACKEND_URL} />,
}, {
  path: '/auth/admin/billing',
  element: <BillingAdmin backendUrl={BACKEND_URL} />,
}, {
  path: '*',
  element: <App />,
  errorElement: <WebsiteRenderFailure />,
}])
const root = ReactDOM.createRoot(document.getElementById('root'), websiteRouter ? {
  onCaughtError(error, info) { if (isAdminPath()) console.error(error, info) }
} : undefined);
// Vite dispatches this for failed lazy chunks. Unmount the old page safely;
// there is no automatic reload or repeat of the failed operation.
if (websiteRouter) window.addEventListener('vite:preloadError', event => {
  if (isAdminPath()) return;
  event.preventDefault();
  root.render(<WebsiteRenderFailure />);
});
root.render(<React.StrictMode>
    {websiteRouter ? <WebsiteMounted><RouterProvider router={websiteRouter} onError={reportRouterError} /></WebsiteMounted> : <BrowserRouter><App /></BrowserRouter>}
  </React.StrictMode>);
