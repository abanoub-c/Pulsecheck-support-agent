import { AlertCircle, Check, LoaderCircle, RefreshCw, X } from 'lucide-react';
import type { ReactNode } from 'react';

export function PageIntro({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-intro">
    <div><div className="page-eyebrow">{eyebrow ?? 'Pulsecheck Support'}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {actions && <div className="page-intro-actions">{actions}</div>}
  </div>;
}

export function StatusChip({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' }) {
  return <span className={`status-chip status-${tone}`}><span className="status-dot" />{children}</span>;
}
export function Button({ children, variant = 'primary', className = '', ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }) {
  return <button className={`button button-${variant} ${className}`} {...props}>{children}</button>;
}
export function Skeleton({ className = '' }: { className?: string }) { return <div className={`skeleton ${className}`} aria-hidden="true" />; }
export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Check size={19} /></span><h3>{title}</h3>{description && <p>{description}</p>}{action}</div>;
}
export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="error-state" role="alert"><span className="error-icon"><AlertCircle size={18} /></span><div><strong>Something went wrong</strong><p>{message}</p><button className="text-button" onClick={onRetry}><RefreshCw size={14} /> Retry</button></div></div>;
}
export function Spinner({ label = 'Loading' }: { label?: string }) { return <span className="spinner-wrap"><LoaderCircle className="spin" size={17} /><span>{label}</span></span>; }
export function IconClose({ onClick, label = 'Close' }: { onClick: () => void; label?: string }) { return <button className="icon-button" onClick={onClick} aria-label={label}><X size={17} /></button>; }
