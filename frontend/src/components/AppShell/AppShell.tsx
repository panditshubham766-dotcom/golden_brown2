import styles from './AppShell.module.css';

interface AppShellProps {
  children: React.ReactNode;
  headerRight?: React.ReactNode;
}

export function AppShell({ children, headerRight }: AppShellProps) {
  return (
    <div className={styles.shell}>
      <header className={styles.header} role="banner">
        <div className={styles.logo} aria-label="LexiGuard home">
          <div className={styles.logoIcon} aria-hidden="true">L</div>
          <span className={styles.logoText}>
            Lexi<span>Guard</span>
          </span>
        </div>
        <div className={styles.headerSpacer} />
        <div className={styles.headerMeta}>
          {headerRight}
        </div>
      </header>
      <main className={styles.main} role="main">
        {children}
      </main>
    </div>
  );
}
