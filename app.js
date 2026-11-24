const form = document.querySelector('#vent-form');
const applicationSelect = document.querySelector('#application');
const messageInput = document.querySelector('#message');
const submitButton = document.querySelector('#submit-button');
const feedback = document.querySelector('#form-feedback');
const statusContainer = document.querySelector('#application-status');
const historyContainer = document.querySelector('#history');
const historyCount = document.querySelector('#history-count');
const charCount = document.querySelector('#char-count');

const states = {
  calm: { label: 'Tranquilo', icon: '●' },
  uneasy: { label: 'Algo inquieto', icon: '●' },
  hot: { label: 'Caliente', icon: '●' },
  fire: { label: 'En llamas', icon: '🔥' },
};

let currentSnapshot = null;
let submitting = false;
let clockOffset = 0;
let refreshTimer = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showFeedback(message, isError = false) {
  feedback.textContent = message;
  feedback.classList.toggle('error', isError);
}

function formatDate(value) {
  return new Intl.DateTimeFormat('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function render(snapshot) {
  currentSnapshot = snapshot;
  clockOffset = Date.parse(snapshot.server_time) - Date.now();
  const selectedId = applicationSelect.value;
  applicationSelect.replaceChildren();
  snapshot.applications.forEach((application) => {
    const option = element('option', '', application.name);
    option.value = application.id;
    applicationSelect.append(option);
  });
  if (snapshot.applications.some((application) => String(application.id) === selectedId)) {
    applicationSelect.value = selectedId;
  }
  applicationSelect.disabled = snapshot.applications.length === 0;
  submitButton.disabled = submitting || snapshot.applications.length === 0;
  renderStatus();
  renderHistory();
  scheduleRefresh();
}

function renderStatus() {
  statusContainer.replaceChildren();
  for (const application of currentSnapshot.applications) {
    const state = states[application.state] || states.calm;
    const tile = element('div', `application-tile state-${application.state}`);
    const top = element('div', 'application-top');
    const icon = element('div', 'application-icon', application.name.charAt(0).toUpperCase());
    icon.setAttribute('aria-hidden', 'true');
    if (application.name === 'aXet.code') {
      const image = element('img', 'application-icon-image');
      image.src = '/iconosAplicaciones/axet.png';
      image.alt = '';
      image.addEventListener('load', () => icon.replaceChildren(image));
    }
    top.append(icon, element('div', 'application-name', application.name), element('span', 'state-badge', `${state.icon}  ${state.label}`));
    const detail = element('div', 'state-detail');
    detail.append(element('strong', '', `${application.active} ${application.active === 1 ? 'desahogo activo' : 'desahogos activos'}`));
    let remaining = 'Todo en calma';
    if (application.next_decay) {
      const minutes = Math.max(1, Math.ceil((Date.parse(application.next_decay) - (Date.now() + clockOffset)) / 60000));
      remaining = `Se calma en ${minutes} min`;
    }
    detail.append(element('span', '', remaining));
    const meter = element('div', 'meter');
    meter.setAttribute('aria-hidden', 'true');
    for (let index = 0; index < 6; index += 1) {
      meter.append(element('span', index < Math.min(application.active, 6) ? 'filled' : ''));
    }
    tile.append(top, detail, meter);
    statusContainer.append(tile);
  }
}

function renderHistory() {
  const entries = currentSnapshot.applications.flatMap((application) => application.history.map((entry) => ({ ...entry, application: application.name })));
  entries.sort((first, second) => Date.parse(second.created_at) - Date.parse(first.created_at) || second.id - first.id);
  historyCount.textContent = `${entries.length} EN TOTAL`;
  historyContainer.replaceChildren();
  if (!entries.length) {
    const empty = element('div', 'empty-state');
    empty.append(element('strong', '', 'Por aquí todo en calma.'), document.createTextNode('Cuando necesites desahogarte, este será tu espacio.'));
    historyContainer.append(empty);
    return;
  }
  for (const entry of entries) {
    const item = element('article', 'history-item');
    const header = element('div', 'history-item-header');
    const date = element('time', 'history-date', formatDate(entry.created_at));
    date.dateTime = entry.created_at;
    header.append(element('span', 'history-app', entry.application), date);
    item.append(header, element('p', 'history-message', entry.message));
    historyContainer.append(item);
  }
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  const now = Date.now() + clockOffset;
  const nextDecay = currentSnapshot.applications
    .map((application) => application.next_decay && Date.parse(application.next_decay))
    .filter((value) => value && value > now);
  const delay = nextDecay.length ? Math.min(60000, Math.max(1000, Math.min(...nextDecay) - now + 100)) : 60000;
  refreshTimer = setTimeout(loadState, delay);
}

async function loadState() {
  try {
    const response = await fetch('/api/state', { cache: 'no-store' });
    if (!response.ok) throw new Error('No se pudo cargar el estado.');
    render(await response.json());
    if (feedback.classList.contains('error') && !submitting) showFeedback('');
  } catch {
    showFeedback('No se puede conectar con la aplicación local. Comprueba que sigue abierta.', true);
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(loadState, 10000);
  }
}

messageInput.addEventListener('input', () => {
  charCount.textContent = `${[...messageInput.value].length} / 2000`;
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) {
    showFeedback('Escribe algo antes de soltarlo.', true);
    messageInput.focus();
    return;
  }
  submitting = true;
  submitButton.disabled = true;
  showFeedback('');
  try {
    const response = await fetch('/api/venting', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ application_id: Number(applicationSelect.value), message }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudo guardar el desahogo.');
    messageInput.value = '';
    charCount.textContent = '0 / 2000';
    render(data);
    showFeedback('Desahogo guardado. Respira, ya está fuera.');
    messageInput.focus();
  } catch (error) {
    showFeedback(error.message || 'No se pudo guardar el desahogo. Inténtalo de nuevo.', true);
  } finally {
    submitting = false;
    submitButton.disabled = !currentSnapshot || currentSnapshot.applications.length === 0;
  }
});

loadState();
