/* Shared console status and workspace labels. No robot commands. */
(() => {
  const states = {
    connecting: ['LINK CONNECTING', 'reconnecting'],
    online: ['LINK ONLINE', ''],
    offline: ['LINK OFFLINE', 'disconnected'],
    reconnecting: ['LINK RETRYING', 'reconnecting'],
    degraded: ['LINK DEGRADED', 'reconnecting'],
  };
  window.setConsoleConnection = (state, fixture = false) => {
    const [label, css] = states[state] || states.offline;
    const indicator = document.getElementById('connIndicator');
    const dot = document.getElementById('connDot');
    const text = document.getElementById('connLabel');
    const value = fixture ? label.replace('LINK', 'PREVIEW') : label;
    if (dot) dot.className = `conn-dot ${css}`.trim();
    if (text) text.textContent = value;
    if (indicator) {
      indicator.dataset.connection = state;
      indicator.setAttribute('aria-label', value);
      indicator.title = fixture ? 'Simulated connection for design review' : 'Browser connection to the TARS console server';
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    const workspaces = [
      ['chat', 'CHAT / COMMUNICATIONS', 'TEXT + VOICE CHANNEL'],
      ['motion', 'MOTION / CONTROL', 'REMOTE + BUILDER + SERVOS'],
      ['emotions', 'EMOTIONS / CHARACTER', 'EXPRESSION + IDENTITY'],
      ['dashboard', 'DASHBOARD / TELEMETRY', 'MEMORY + SYSTEMS'],
      ['config', 'CONFIG / SETTINGS', 'SYSTEM CONFIGURATION'],
    ];
    function select(index) {
      document.getElementById('workspaceIndex').textContent = String(index + 1).padStart(2, '0');
      document.getElementById('workspaceName').textContent = workspaces[index][1];
      document.getElementById('workspaceDetail').textContent = workspaces[index][2];
      document.querySelectorAll('.mobile-nav-btn').forEach((button, i) => {
        if (i === index) button.setAttribute('aria-current', 'page');
        else button.removeAttribute('aria-current');
      });
      workspaces.forEach(([id], i) => {
        const pane = document.getElementById(id);
        // Mobile lays all panes side by side; keep off-screen controls out of
        // keyboard navigation and the accessibility tree.
        pane.inert = i !== index;
        pane.setAttribute('aria-labelledby', `${id}-tab`);
      });
    }
    workspaces.forEach(([id], index) => {
      document.getElementById(`${id}-tab`).addEventListener('shown.bs.tab', () => select(index));
    });
    select(0);
  });
})();
