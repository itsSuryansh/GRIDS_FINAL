import React from 'react'

/** Instrument panel container with a compact technical header. */
export default function Panel({
  title,
  subtitle = null,
  icon: Icon,
  actions = null,
  children,
  className = '',
  bodyClassName = '',
  dense = false,
  scroll = false,
}) {
  return (
    <section className={`panel flex flex-col min-h-0 ${className}`}>
      {(title || actions) && (
        <header className="panel-header shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            {Icon ? <Icon size={14} className="text-slate-400 shrink-0" /> : null}
            <div className="min-w-0">
              <h2 className="panel-title truncate">{title}</h2>
              {subtitle ? <p className="text-2xs text-slate-400 truncate">{subtitle}</p> : null}
            </div>
          </div>
          {actions ? <div className="flex items-center gap-1.5 shrink-0">{actions}</div> : null}
        </header>
      )}
      <div className={`${dense ? 'p-0' : 'p-3'} min-h-0 flex-1 ${scroll ? 'overflow-y-auto' : ''} ${bodyClassName}`}>
        {children}
      </div>
    </section>
  )
}
