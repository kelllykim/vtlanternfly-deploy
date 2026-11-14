import { createContext, useContext, useEffect, useId, useRef, useState } from 'react'

export const LogoutContext = createContext<() => void>(() => {})

export default function AccountMenu() {
    const logout = useContext(LogoutContext)
    const [open, setOpen] = useState(false)
    const container = useRef<HTMLDivElement>(null)
    const trigger = useRef<HTMLButtonElement>(null)
    const panelId = useId()

    useEffect(() => {
        if (!open) return
        const dismiss = (event: PointerEvent) => {
            if (!container.current?.contains(event.target as Node)) setOpen(false)
        }
        const escape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                setOpen(false)
                trigger.current?.focus()
            }
        }
        document.addEventListener('pointerdown', dismiss)
        document.addEventListener('keydown', escape)
        return () => {
            document.removeEventListener('pointerdown', dismiss)
            document.removeEventListener('keydown', escape)
        }
    }, [open])

    return <div className="account-menu" ref={container} onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false)
    }}>
        <button ref={trigger} type="button" className="header-mark" aria-label="Account options"
            aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(value => !value)}>
            <span>VT</span>
        </button>
        {open && <div className="account-menu-panel" id={panelId}>
            <button type="button" onClick={() => { setOpen(false); logout() }}>Log out</button>
        </div>}
    </div>
}
