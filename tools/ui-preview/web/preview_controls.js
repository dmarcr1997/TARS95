(() => {
  const defaults = { machine_state: 'standby', battery: 95, alert: 'none', connectivity: 'online' };
  let current = { ...defaults };
  let requestNumber = 0;

  const byId = (id) => document.getElementById(id);
  const consoleEl = byId('previewConsole');
  const statusEl = byId('previewSaveStatus');
  const readout = byId('previewReadout');

  function paint(state) {
    current = { ...current, ...state };
    document.body.dataset.previewState = current.machine_state;
    document.body.dataset.previewAlert = current.alert;
    document.body.dataset.previewConnectivity = current.connectivity;

    document.querySelectorAll('[data-preview-field="machine_state"]').forEach((button) => {
      const active = button.dataset.previewValue === current.machine_state;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    byId('previewBattery').value = current.battery;
    byId('previewBatteryValue').textContent = `${String(current.battery).padStart(3, '0')}%`;
    byId('previewAlert').value = current.alert;
    byId('previewConnectivity').value = current.connectivity;

    byId('previewReadoutState').textContent = current.machine_state.toUpperCase();
    byId('previewReadoutBattery').textContent = `BAT ${String(current.battery).padStart(3, '0')}%`;
    byId('previewReadoutAlert').textContent = current.alert === 'none' ? 'NO ALERT' : current.alert.toUpperCase();
    byId('previewReadoutLink').textContent = `LINK ${current.connectivity.toUpperCase()}`;
    readout.className = `preview-readout is-${current.alert} is-${current.connectivity}`;

    const connDot = byId('connDot');
    if (connDot) connDot.className = current.connectivity === 'offline' ? 'conn-dot disconnected' : 'conn-dot';
  }

  async function update(changes) {
    const thisRequest = ++requestNumber;
    statusEl.textContent = 'APPLYING…';
    try {
      const response = await fetch('/api/preview/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'State rejected');
      if (thisRequest === requestNumber) paint(data.state);
      statusEl.textContent = 'FIXTURES UPDATED';
    } catch (error) {
      statusEl.textContent = `ERROR: ${error.message}`;
    }
  }

  document.querySelectorAll('[data-preview-field]').forEach((button) => {
    button.addEventListener('click', () => update({ [button.dataset.previewField]: button.dataset.previewValue }));
  });
  byId('previewBattery').addEventListener('input', (event) => {
    byId('previewBatteryValue').textContent = `${String(event.target.value).padStart(3, '0')}%`;
  });
  byId('previewBattery').addEventListener('change', (event) => update({ battery: Number(event.target.value) }));
  byId('previewAlert').addEventListener('change', (event) => update({ alert: event.target.value }));
  byId('previewConnectivity').addEventListener('change', (event) => update({ connectivity: event.target.value }));
  byId('previewReset').addEventListener('click', () => update(defaults));
  byId('previewToggle').addEventListener('click', () => {
    const collapsed = consoleEl.classList.toggle('is-collapsed');
    byId('previewToggle').setAttribute('aria-expanded', String(!collapsed));
  });

  fetch('/api/preview/state').then((response) => response.json()).then((data) => paint(data.state)).catch(() => {
    statusEl.textContent = 'FIXTURE LINK ERROR';
  });
})();
