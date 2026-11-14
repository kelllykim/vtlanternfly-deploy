import { useEffect, useId, useRef, useState } from 'react'

export default function MajorSelect({ value, options, disabled, loading, onChange }: {
    value: string; options: string[]; disabled: boolean; loading: boolean; onChange: (major: string) => void
}) {
    const [query, setQuery] = useState(value)
    const [open, setOpen] = useState(false)
    const [active, setActive] = useState(0)
    const input = useRef<HTMLInputElement>(null)
    const list = useRef<HTMLUListElement>(null)
    const id = useId()
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
    const matches = options.filter(option => words.every(word => option.toLowerCase().includes(word)))

    useEffect(() => {
        input.current?.setCustomValidity(query.trim() && !value ? 'Choose a major from the matching options, or clear this optional field.' : '')
    }, [query, value])

    useEffect(() => {
        if (open) list.current?.children[active]?.scrollIntoView({ block: 'nearest' })
    }, [active, open])

    const choose = (major: string) => {
        setQuery(major)
        onChange(major)
        setOpen(false)
    }

    return <div className="major-select">
        <label htmlFor={id}>Major (optional)</label>
        <input ref={input} id={id} type="text" role="combobox" autoComplete="off"
            aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-options`}
            aria-activedescendant={open && matches.length ? `${id}-option-${active}` : undefined}
            placeholder={loading ? 'Loading majors…' : 'Type to search majors'}
            value={query} disabled={disabled}
            onFocus={() => { setOpen(true); setActive(0) }} onBlur={() => setOpen(false)}
            onChange={event => {
                const text = event.target.value
                setQuery(text)
                onChange(options.find(option => option.toLowerCase() === text.trim().toLowerCase()) || '')
                setActive(0)
                setOpen(true)
            }}
            onKeyDown={event => {
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault()
                    setOpen(true)
                    setActive(index => matches.length ? (index + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length : 0)
                } else if (event.key === 'Enter' && open && matches.length) {
                    event.preventDefault()
                    choose(matches[active] || matches[0])
                } else if (event.key === 'Escape') {
                    event.preventDefault()
                    setOpen(false)
                } else if (event.key === 'Tab') {
                    setOpen(false)
                }
            }} />
        {open && <ul ref={list} id={`${id}-options`} role="listbox" className="major-options">
            {matches.length ? matches.map((major, index) =>
                <li id={`${id}-option-${index}`} key={major} role="option" aria-selected={value === major}
                    className={index === active ? 'highlighted' : ''}
                    onMouseDown={event => event.preventDefault()} onClick={() => choose(major)}>
                    {major}
                </li>) : <li role="presentation">No matching majors. Try another search.</li>}
        </ul>}
    </div>
}
