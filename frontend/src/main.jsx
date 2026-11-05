import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import { BrowserRouter, createBrowserRouter, RouterProvider } from 'react-router-dom';
import WebsiteRenderFailure, { WebsiteMounted } from './auth/WebsiteRenderFailure';
import SubscriptionAdmin from './auth/SubscriptionAdmin';
import BillingAdmin from './auth/BillingAdmin';

const isAdminPath = () => window.location.pathname.toLowerCase().startsWith('/auth/admin/')
const websiteRouter = window.electronAPI ? null : createBrowserRouter([{
  path: '/auth/admin/subscriptions',
  element: <SubscriptionAdmin />,
}, {
  path: '/auth/admin/billing',
  element: <BillingAdmin />,
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
    {websiteRouter ? <WebsiteMounted><RouterProvider router={websiteRouter} /></WebsiteMounted> : <BrowserRouter><App /></BrowserRouter>}
  </React.StrictMode>);
