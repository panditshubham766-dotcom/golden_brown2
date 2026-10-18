import styles from './Button.module.css';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  iconOnly?: boolean;
  children: React.ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  iconOnly = false,
  disabled,
  children,
  className,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;

  const classes = [
    styles.btn,
    styles[variant],
    size !== 'md' ? styles[size] : '',
    iconOnly ? styles.iconOnly : '',
    className ?? '',
  ].filter(Boolean).join(' ');

  return (
    <button
      className={classes}
      disabled={isDisabled}
      aria-disabled={isDisabled ? true : undefined}
      aria-busy={loading ? true : undefined}
      {...rest}
    >
      {loading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}
