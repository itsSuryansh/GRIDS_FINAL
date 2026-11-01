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
  tone = 'default',
}) {
  const accent =
    tone === 'alert' ? 'before:bg-red-500'
      : tone === 'warn' ? 'before:bg-amber-500'
        : tone === 'good' ? 'before:bg-emerald-500'
          : tone === 'accent' ? 'before:bg-blue-600' : 'before:bg-transparent'
  return (
    <section className={`panel relative flex flex-col min-h-0 ${className}`}>
      <span className={`absolute left-0 top-0 h-full w-[2px] ${accent.replace('before:', '')}`} aria-hidden />
      {(title || actions) && (
        <header className="panel-header shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            {Icon ? (
              <span className="grid place-items-center h-[21px] w-[21px] rounded-md bg-slate-100/90 text-slate-500 shrink-0">
                <Icon size={11.5} strokeWidth={2.4} />
              </span>
            ) : null}
            <div className="min-w-0 leading-none">
              <h2 className="panel-title truncate">{title}</h2>
              {subtitle ? <p className="text-[9.5px] text-slate-400 truncate mt-[3px] leading-none">{subtitle}</p> : null}
            </div>
          </div>
          {actions ? <div className="flex items-center gap-1.5 shrink-0">{actions}</div> : null}
        </header>
      )}
      <div className={`${dense ? 'p-0' : 'p-3'} min-h-0 flex-1 ${scroll ? 'overflow-y-auto scroll-quiet' : ''} ${bodyClassName}`}>
        {children}
      </div>
    </section>
  )
}
