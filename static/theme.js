document.addEventListener('DOMContentLoaded', () => {
    // 1. Check LocalStorage or System Preference
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    let currentTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');

    // 2. Apply Theme
    applyTheme(currentTheme);

    // 3. Create Toggle Button if it doesn't exist
    if (!document.querySelector('.theme-toggle')) {
        const btn = document.createElement('button');
        btn.className = 'theme-toggle';
        btn.innerHTML = currentTheme === 'dark' ? '☀️' : '🌙';
        btn.onclick = toggleTheme;
        document.body.appendChild(btn);
    }
});

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);

    // Update button icon if exists
    const btn = document.querySelector('.theme-toggle');
    if (btn) {
        btn.innerHTML = theme === 'dark' ? '☀️' : '🌙'; // Sun for dark mode (switch to light), Moon for light mode
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
}
