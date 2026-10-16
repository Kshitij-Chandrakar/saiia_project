import React, { useEffect, useId, useRef, useState } from 'react'
import { LayoutDashboard, LogOut, User } from 'lucide-react'
import choiceMenuUrl from '../assets/startup-choice/choice-menu.svg'
import './startup-account-menu.css'

export default function StartupAccountMenu({ authenticatedEmail = '', onSignedOut, disabled = false }) {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false)
  const [accountMenuAction, setAccountMenuAction] = useState('')
  const [accountMenuError, setAccountMenuError] = useState('')
  const accountMenuShellRef = useRef(null)
  const accountMenuTriggerRef = useRef(null)
  const accountMenuItemRefs = useRef([])
  const actionPendingRef = useRef(false)
  const mountedRef = useRef(false)
  const menuId = useId()
  const safeAuthenticatedEmail = typeof authenticatedEmail === 'string' ? authenticatedEmail.trim() : ''
  const accountIdentityReady = Boolean(safeAuthenticatedEmail)
  const saiiaApi = window.saiia
  const electronApi = window.electronAPI
  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false } }, [])
  useEffect(() => {
    setAccountMenuOpen(false)
    setAccountMenuError('')
  }, [safeAuthenticatedEmail])

  useEffect(() => {
    if (!accountMenuOpen) {
      return undefined
    }
    const firstEnabledItem = accountMenuItemRefs.current.find((item) => item && !item.disabled)
    firstEnabledItem?.focus()

    const handleOutsidePointer = (event) => {
      if (!accountMenuShellRef.current?.contains(event.target)) {
        setAccountMenuOpen(false)
      }
    }
    const handleDocumentKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setAccountMenuOpen(false)
        accountMenuTriggerRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', handleOutsidePointer)
    document.addEventListener('keydown', handleDocumentKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handleOutsidePointer)
      document.removeEventListener('keydown', handleDocumentKeyDown)
    }
  }, [accountMenuOpen])

  const handleAccountMenuKeyDown = (event) => {
    const items = accountMenuItemRefs.current.filter((item) => item && !item.disabled)
    if (!items.length) {
      return
    }
    const currentIndex = items.indexOf(document.activeElement)
    let nextIndex = currentIndex
    if (event.key === 'ArrowDown') {
      nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % items.length
    } else if (event.key === 'ArrowUp') {
      nextIndex = currentIndex <= 0 ? items.length - 1 : currentIndex - 1
    } else if (event.key === 'Home') {
      nextIndex = 0
    } else if (event.key === 'End') {
      nextIndex = items.length - 1
    } else {
      return
    }
    event.preventDefault()
    items[nextIndex]?.focus()
  }

  const handleOpenDashboard = async () => {
    if (actionPendingRef.current || disabled || !accountIdentityReady) {
      return
    }
    const openDashboard = saiiaApi?.openDashboard || electronApi?.openDashboard
    if (typeof openDashboard !== 'function') {
      setAccountMenuError('Dashboard is unavailable right now. Please try again.')
      return
    }
    actionPendingRef.current = true
    setAccountMenuAction('dashboard')
    setAccountMenuError('')
    try {
      const result = await openDashboard()
      if (!mountedRef.current) return
      if (result?.ok === false) {
        throw new Error('Dashboard unavailable')
      }
      setAccountMenuOpen(false)
    } catch {
      if (mountedRef.current) setAccountMenuError('We could not open the dashboard. Please try again.')
    } finally {
      actionPendingRef.current = false
      if (mountedRef.current) setAccountMenuAction('')
    }
  }

  const handleLogout = async () => {
    if (actionPendingRef.current || disabled || !accountIdentityReady) {
      return
    }
    const logoutAuth = saiiaApi?.logoutAuth || electronApi?.logoutAuth
    if (typeof logoutAuth !== 'function') {
      setAccountMenuError('Sign out is unavailable right now. Please try again.')
      return
    }
    actionPendingRef.current = true
    setAccountMenuAction('logout')
    setAccountMenuError('')
    try {
      const result = await logoutAuth()
      if (result?.status === 'signed-out' || result?.status === 'token-expired') {
        if (mountedRef.current) setAccountMenuOpen(false)
        onSignedOut?.(result)
        return
      }
      if (mountedRef.current) setAccountMenuError('We could not sign you out. Please try again.')
    } catch {
      if (mountedRef.current) setAccountMenuError('We could not sign you out. Please try again.')
    } finally {
      actionPendingRef.current = false
      if (mountedRef.current) setAccountMenuAction('')
    }
  }

  if (!accountIdentityReady) return null
  return (
<div className="startup-choice-account-menu-shell" ref={accountMenuShellRef}>
              <button
                className="startup-choice-icon-button startup-choice-account-trigger"
                type="button"
                ref={accountMenuTriggerRef}
                aria-label="Account menu"
                aria-haspopup="menu"
                aria-expanded={accountMenuOpen}
                aria-controls={menuId}
                disabled={disabled || Boolean(accountMenuAction)}
                onClick={() => {
                  setAccountMenuError('')
                  setAccountMenuOpen((open) => !open)
                }}
              >
                <img src={choiceMenuUrl} alt="" aria-hidden="true" />
              </button>

              {accountMenuOpen ? (
                <div
                  className="startup-choice-account-menu"
                  id={menuId}
                  role="menu"
                  aria-label="Account actions"
                  onKeyDown={handleAccountMenuKeyDown}
                >
                  <div className="startup-choice-account-menu__identity">
                    <User size={17} aria-hidden="true" />
                    <span className="startup-choice-account-menu__identity-copy">
                      <strong>Intervucopilot</strong>
                      <span
                        title={safeAuthenticatedEmail || 'Account unavailable'}
                        aria-label={safeAuthenticatedEmail || 'Account unavailable'}
                      >
                        {safeAuthenticatedEmail || 'Account unavailable'}
                      </span>
                    </span>
                  </div>
                  <div className="startup-choice-account-menu__divider" />
                  <button
                    type="button"
                    role="menuitem"
                    className="startup-choice-account-menu__item"
                    ref={(node) => {
                      accountMenuItemRefs.current[0] = node
                    }}
                    disabled={!accountIdentityReady || Boolean(accountMenuAction)}
                    onClick={() => void handleOpenDashboard()}
                  >
                    <LayoutDashboard size={17} aria-hidden="true" />
                    <span>{accountMenuAction === 'dashboard' ? 'Opening Dashboard...' : 'Dashboard'}</span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="startup-choice-account-menu__item startup-choice-account-menu__item--danger"
                    ref={(node) => {
                      accountMenuItemRefs.current[1] = node
                    }}
                    disabled={!accountIdentityReady || Boolean(accountMenuAction)}
                    onClick={() => void handleLogout()}
                  >
                    <LogOut size={17} aria-hidden="true" />
                    <span>{accountMenuAction === 'logout' ? 'Signing out...' : 'Log out'}</span>
                  </button>
                  {accountMenuError ? (
                    <p className="startup-choice-account-menu__error" role="alert">{accountMenuError}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
  )
}
