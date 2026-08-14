// State variables
let appData = null;
let currentYear = 2026;
let currentMonth = 7; // 0-indexed (7 = August)
let selectedDateStr = null;
let currentFilter = 'ALL';
let searchQuery = '';

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

// DOM Elements
const currentMonthLabel = document.getElementById('current-month-label');
const prevMonthBtn = document.getElementById('prev-month-btn');
const nextMonthBtn = document.getElementById('next-month-btn');
const todayBtn = document.getElementById('today-btn');
const calendarDaysGrid = document.getElementById('calendar-days-grid');

const kpiTotalEps = document.getElementById('kpi-total-eps');
const kpiGreenRate = document.getElementById('kpi-green-rate');
const kpiRedRate = document.getElementById('kpi-red-rate');
const kpiSelectedCount = document.getElementById('kpi-selected-count');
const kpiSelectedDateLabel = document.getElementById('kpi-selected-date-label');
const lastUpdatedLabel = document.getElementById('last-updated');

const selectedDateHeading = document.getElementById('selected-date-heading');
const selectedDateSubheading = document.getElementById('selected-date-subheading');
const epTableBody = document.getElementById('ep-table-body');
const symbolSearchInput = document.getElementById('symbol-search');
const filterChips = document.querySelectorAll('.filter-chip');

// Initialize App
async function initApp() {
  try {
    const res = await fetch('data/ep_calendar_data.json');
    if (!res.ok) throw new Error('Failed to load JSON data');
    appData = await res.json();
    
    lastUpdatedLabel.textContent = `Updated: ${appData.last_updated || 'Live'}`;
    calculateKPIs();

    // Set initial date to latest date in dataset
    const dates = Object.keys(appData.calendar).sort().reverse();
    if (dates.length > 0) {
      const latestDate = new Date(dates[0]);
      currentYear = latestDate.getFullYear();
      currentMonth = latestDate.getMonth();
      selectedDateStr = dates[0];
    }

    renderCalendar();
    if (selectedDateStr) renderSelectedDateDetails(selectedDateStr);

    setupEventListeners();
  } catch (err) {
    console.error(err);
    calendarDaysGrid.innerHTML = `<div class="empty-msg" style="grid-column: 1/-1;">Failed to load EP calendar data. Please ensure data/ep_calendar_data.json is present.</div>`;
  }
}

// Calculate Summary KPIs
function calculateKPIs() {
  if (!appData || !appData.calendar) return;

  let totalEps = 0;
  let greenCount = 0;
  let redCount = 0;

  Object.values(appData.calendar).forEach(dayObj => {
    dayObj.ep_list.forEach(ep => {
      totalEps++;
      if (ep.d1_status === 'GREEN') greenCount++;
      if (ep.d1_status === 'RED') redCount++;
    });
  });

  kpiTotalEps.textContent = totalEps;
  kpiGreenRate.textContent = totalEps > 0 ? `${((greenCount / totalEps) * 100).toFixed(1)}%` : '0%';
  kpiRedRate.textContent = totalEps > 0 ? `${((redCount / totalEps) * 100).toFixed(1)}%` : '0%';
}

// Render Monthly Calendar Grid
function renderCalendar() {
  currentMonthLabel.textContent = `${MONTH_NAMES[currentMonth]} ${currentYear}`;
  calendarDaysGrid.innerHTML = '';

  const firstDayOfMonth = new Date(currentYear, currentMonth, 1);
  const lastDayOfMonth = new Date(currentYear, currentMonth + 1, 0);
  
  // Get starting day index (Mon = 0, Sun = 6)
  let startDayIndex = firstDayOfMonth.getDay() - 1;
  if (startDayIndex === -1) startDayIndex = 6;

  const totalDays = lastDayOfMonth.getDate();

  // Previous month trailing padding
  const prevMonthLastDay = new Date(currentYear, currentMonth, 0).getDate();
  for (let i = startDayIndex - 1; i >= 0; i--) {
    const dayNum = prevMonthLastDay - i;
    const cell = document.createElement('div');
    cell.className = 'day-cell other-month';
    cell.innerHTML = `<span class="day-number">${dayNum}</span>`;
    calendarDaysGrid.appendChild(cell);
  }

  // Current month days
  for (let day = 1; day <= totalDays; day++) {
    const formattedMonth = String(currentMonth + 1).padStart(2, '0');
    const formattedDay = String(day).padStart(2, '0');
    const dateStr = `${currentYear}-${formattedMonth}-${formattedDay}`;

    const cell = document.createElement('div');
    cell.className = 'day-cell';

    if (dateStr === selectedDateStr) cell.classList.add('selected');

    const dayData = appData.calendar[dateStr];

    let contentHtml = `<span class="day-number">${day}</span>`;

    if (dayData && dayData.count > 0) {
      cell.classList.add('has-ep');
      
      // Filter EP list based on active filter
      const filteredEps = dayData.ep_list.filter(ep => {
        if (currentFilter === 'ALL') return true;
        return ep.d1_status === currentFilter;
      });

      if (filteredEps.length > 0) {
        contentHtml += `
          <div class="ep-badge-container">
            <span class="ep-count-pill">${filteredEps.length} EP${filteredEps.length > 1 ? 's' : ''}</span>
            <div class="status-dots">
              ${filteredEps.slice(0, 5).map(ep => `<span class="dot-indicator ${ep.d1_status.toLowerCase()}"></span>`).join('')}
            </div>
          </div>
        `;
      }
    }

    cell.innerHTML = contentHtml;

    cell.addEventListener('click', () => {
      document.querySelectorAll('.day-cell').forEach(c => c.classList.remove('selected'));
      cell.classList.add('selected');
      selectedDateStr = dateStr;
      renderSelectedDateDetails(dateStr);
    });

    calendarDaysGrid.appendChild(cell);
  }
}

// Render Selected Date EP Table Details
function renderSelectedDateDetails(dateStr) {
  const dayData = appData.calendar[dateStr];
  
  kpiSelectedDateLabel.textContent = dateStr;

  if (!dayData || dayData.count === 0) {
    selectedDateHeading.textContent = `No Episodic Pivots on ${dateStr}`;
    selectedDateSubheading.textContent = 'No stocks met the breakout criteria on this trading day.';
    kpiSelectedCount.textContent = '0';
    epTableBody.innerHTML = `<tr><td colspan="10" class="empty-msg">No Episodic Pivots recorded for ${dateStr}.</td></tr>`;
    return;
  }

  let epList = dayData.ep_list;

  // Filter by status
  if (currentFilter !== 'ALL') {
    epList = epList.filter(ep => ep.d1_status === currentFilter);
  }

  // Search by symbol
  if (searchQuery.trim() !== '') {
    epList = epList.filter(ep => ep.symbol.toLowerCase().includes(searchQuery.toLowerCase()));
  }

  kpiSelectedCount.textContent = epList.length;
  selectedDateHeading.textContent = `Episodic Pivots for ${dateStr} (${epList.length} Stock${epList.length > 1 ? 's' : ''})`;
  selectedDateSubheading.textContent = `Breakout stocks identified on ${dateStr} with D+1 Retained EP Gain metrics`;

  if (epList.length === 0) {
    epTableBody.innerHTML = `<tr><td colspan="12" class="empty-msg">No stocks match the current filter or search criteria for ${dateStr}.</td></tr>`;
    return;
  }

  epTableBody.innerHTML = epList.map((ep, idx) => {
    const statusClass = `badge-${ep.d1_status.toLowerCase()}`;
    const retainedGainText = ep.d1_retained_gain_pct !== null ? `${ep.d1_retained_gain_pct}%` : 'N/A';
    const d1CloseText = ep.d1_close ? `₹${ep.d1_close.toFixed(2)}` : 'N/A';
    const formattedVol = ep.volume ? ep.volume.toLocaleString('en-IN') : 'N/A';
    const formattedSmaVol = ep.sma_vol_50 ? Math.round(ep.sma_vol_50).toLocaleString('en-IN') : 'N/A';
    const delivPerText = ep.deliv_per ? `${ep.deliv_per}%` : 'N/A';

    return `
      <tr class="stock-row" data-idx="${idx}">
        <td class="symbol-cell">${ep.symbol}</td>
        <td>₹${ep.close.toFixed(2)}</td>
        <td style="color: var(--accent-green); font-weight: 600;">+${ep.change_pct}%</td>
        <td style="color: var(--accent-blue); font-weight: 700;">${ep.vol_ratio}x</td>
        <td>${formattedVol}</td>
        <td>${formattedSmaVol}</td>
        <td>${delivPerText}</td>
        <td>${ep.d1_date || 'N/A'}</td>
        <td>${d1CloseText}</td>
        <td style="font-weight: 700; color: ${ep.d1_retained_gain_pct >= 96 ? 'var(--accent-green)' : (ep.d1_retained_gain_pct < 95 ? 'var(--accent-red)' : 'var(--accent-yellow)')};">${retainedGainText}</td>
        <td><span class="badge ${statusClass}">${ep.d1_status}</span></td>
        <td><button class="view-btn" onclick="openStockModal('${dateStr}', '${ep.symbol}')">Details 🔍</button></td>
      </tr>
    `;
  }).join('');
}

// Open Stock Details Modal
function openStockModal(dateStr, symbol) {
  const dayData = appData.calendar[dateStr];
  if (!dayData) return;
  const ep = dayData.ep_list.find(e => e.symbol === symbol);
  if (!ep) return;

  document.getElementById('modal-symbol').textContent = ep.symbol;
  
  const statusBadge = document.getElementById('modal-status-badge');
  statusBadge.textContent = ep.d1_status;
  statusBadge.className = `badge badge-${ep.d1_status.toLowerCase()}`;

  // Breakout Day Details
  document.getElementById('m-ep-date').textContent = dateStr;
  document.getElementById('m-ep-close').textContent = `₹${ep.close.toFixed(2)}`;
  document.getElementById('m-ep-prev').textContent = `₹${ep.prev_close.toFixed(2)}`;
  document.getElementById('m-ep-change').textContent = `+${ep.change_pct}%`;
  document.getElementById('m-ep-vol').textContent = ep.volume ? ep.volume.toLocaleString('en-IN') : 'N/A';
  document.getElementById('m-ep-smavol').textContent = ep.sma_vol_50 ? Math.round(ep.sma_vol_50).toLocaleString('en-IN') : 'N/A';
  document.getElementById('m-ep-volratio').textContent = `${ep.vol_ratio}x Avg Vol`;
  document.getElementById('m-ep-ohl').textContent = `O: ₹${ep.open_price.toFixed(2)} | H: ₹${ep.high_price.toFixed(2)} | L: ₹${ep.low_price.toFixed(2)}`;
  document.getElementById('m-ep-deliv').textContent = ep.deliv_per ? `${ep.deliv_per}% (${ep.deliv_trend})` : 'N/A';

  // D+1 Details
  document.getElementById('m-d1-date').textContent = ep.d1_date || 'N/A';
  document.getElementById('m-d1-close').textContent = ep.d1_close ? `₹${ep.d1_close.toFixed(2)}` : 'N/A';
  document.getElementById('m-d1-ohl').textContent = ep.d1_open ? `O: ₹${ep.d1_open.toFixed(2)} | H: ₹${ep.d1_high.toFixed(2)} | L: ₹${ep.d1_low.toFixed(2)}` : 'N/A';
  document.getElementById('m-d1-return').textContent = ep.d1_return_pct !== null ? `${ep.d1_return_pct > 0 ? '+' : ''}${ep.d1_return_pct}%` : 'N/A';
  document.getElementById('m-d1-retained').textContent = ep.d1_retained_gain_pct !== null ? `${ep.d1_retained_gain_pct}%` : 'N/A';
  document.getElementById('m-d1-eval').textContent = ep.d1_status === 'GREEN' ? '🟢 GREEN: Retained ≥96% of EP Gain' : (ep.d1_status === 'RED' ? '🔴 RED: Retained <95% of EP Gain' : (ep.d1_status === 'YELLOW' ? '🟡 YELLOW: Retained 95-96% of EP Gain' : '⏳ PENDING'));

  // External Chart Links
  document.getElementById('tradingview-link').href = `https://www.tradingview.com/chart/?symbol=NSE:${ep.symbol}`;
  document.getElementById('nse-link').href = `https://www.nseindia.com/get-quotes/equity?symbol=${ep.symbol}`;

  document.getElementById('stock-modal').classList.add('active');
}

function closeStockModal() {
  document.getElementById('stock-modal').classList.remove('active');
}

// Event Listeners
function setupEventListeners() {
  prevMonthBtn.addEventListener('click', () => {
    currentMonth--;
    if (currentMonth < 0) {
      currentMonth = 11;
      currentYear--;
    }
    renderCalendar();
  });

  nextMonthBtn.addEventListener('click', () => {
    currentMonth++;
    if (currentMonth > 11) {
      currentMonth = 0;
      currentYear++;
    }
    renderCalendar();
  });

  todayBtn.addEventListener('click', () => {
    const dates = Object.keys(appData.calendar).sort().reverse();
    if (dates.length > 0) {
      const latestDate = new Date(dates[0]);
      currentYear = latestDate.getFullYear();
      currentMonth = latestDate.getMonth();
      selectedDateStr = dates[0];
      renderCalendar();
      renderSelectedDateDetails(selectedDateStr);
    }
  });

  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentFilter = chip.getAttribute('data-filter');
      renderCalendar();
      if (selectedDateStr) renderSelectedDateDetails(selectedDateStr);
    });
  });

  symbolSearchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value;
    if (selectedDateStr) renderSelectedDateDetails(selectedDateStr);
  });

  document.getElementById('modal-close-btn').addEventListener('click', closeStockModal);
  document.getElementById('stock-modal').addEventListener('click', (e) => {
    if (e.target.id === 'stock-modal') closeStockModal();
  });
}

// Launch on DOM ready
document.addEventListener('DOMContentLoaded', initApp);
