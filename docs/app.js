// State variables
let appData = null;
let currentView = 'categories'; // 'categories' or 'calendar'
let currentCategory = 'new_eps'; // 'new_eps', 'persistent_eps', 'sustained_eps', 'fizzled_eps'
let categorySearchQuery = '';

let currentYear = 2026;
let currentMonth = 7; // 0-indexed (7 = August)
let selectedDateStr = null;
let currentFilter = 'ALL';
let calendarSearchQuery = '';

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

const CATEGORY_META = {
  new_eps: {
    icon: '🌟',
    title: "Table 1: Today's Episodic Pivots",
    desc: 'All stocks that triggered an Episodic Pivot on the latest market session, with fresh 1st-time vs repeat breakout classification.',
    badgeClass: 'tab-new'
  },
  persistent_eps: {
    icon: '🔁',
    title: 'Table 2: Persistent Episodic Pivots (Repeated in 50 Days)',
    desc: 'Stocks that have triggered multiple Episodic Pivots (≥2 times) in the last 50 days, showing sustained institutional accumulation.',
    badgeClass: 'tab-persistent'
  },
  sustained_eps: {
    icon: '🚀',
    title: 'Table 3: Sustained Episodic Pivots (Holding Gains Above EP1)',
    desc: 'Stocks from the last 50 days whose current market price has sustained and remained strictly ABOVE the 1st Episodic Pivot closing price.',
    badgeClass: 'tab-sustained'
  },
  fizzled_eps: {
    icon: '💨',
    title: 'Table 4: Fizzled Out Episodic Pivots (Breakout Gains Vanished)',
    desc: 'Stocks whose price dropped below the 1st EP Day starting base price (Prev Close). All 1st breakout gains have completely vanished.',
    badgeClass: 'tab-fizzled'
  }
};

// DOM Elements
const kpiNewCount = document.getElementById('kpi-new-count');
const kpiLatestDateLabel = document.getElementById('kpi-latest-date-label');
const kpiPersistentCount = document.getElementById('kpi-persistent-count');
const kpiSustainedRate = document.getElementById('kpi-sustained-rate');
const kpiSustainedCountSub = document.getElementById('kpi-sustained-count-sub');
const kpiFizzledRate = document.getElementById('kpi-fizzled-rate');
const kpiFizzledCountSub = document.getElementById('kpi-fizzled-count-sub');
const lastUpdatedLabel = document.getElementById('last-updated');

const btnViewCategories = document.getElementById('btn-view-categories');
const btnViewCalendar = document.getElementById('btn-view-calendar');
const sectionCategories = document.getElementById('section-categories');
const sectionCalendar = document.getElementById('section-calendar');

const catTabBtns = document.querySelectorAll('.cat-tab-btn');
const badgeNewCount = document.getElementById('badge-new-count');
const badgePersistentCount = document.getElementById('badge-persistent-count');
const badgeSustainedCount = document.getElementById('badge-sustained-count');
const badgeFizzledCount = document.getElementById('badge-fizzled-count');

const bannerIcon = document.getElementById('banner-icon');
const bannerTitle = document.getElementById('banner-title');
const bannerDesc = document.getElementById('banner-desc');
const categorySearchInput = document.getElementById('category-search-input');
const categoryTableHead = document.getElementById('category-table-head');
const categoryTableBody = document.getElementById('category-table-body');

// Calendar DOM Elements
const currentMonthLabel = document.getElementById('current-month-label');
const prevMonthBtn = document.getElementById('prev-month-btn');
const nextMonthBtn = document.getElementById('next-month-btn');
const todayBtn = document.getElementById('today-btn');
const calendarDaysGrid = document.getElementById('calendar-days-grid');
const selectedDateHeading = document.getElementById('selected-date-heading');
const selectedDateSubheading = document.getElementById('selected-date-subheading');
const epTableBody = document.getElementById('ep-table-body');
const symbolSearchInput = document.getElementById('symbol-search');
const filterChips = document.querySelectorAll('.filter-chip');

// Initialize Application
async function initApp() {
  try {
    const timestamp = new Date().getTime();
    const res = await fetch(`data/ep_calendar_data.json?t=${timestamp}`, {
      cache: 'no-store',
      headers: {
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'
      }
    });
    if (!res.ok) throw new Error('Failed to load JSON data');
    appData = await res.json();

    lastUpdatedLabel.textContent = `Updated: ${appData.last_updated || 'Live'}`;
    
    populateKPIs();
    renderCategoryTable();

    // Setup Calendar initial date to latest date
    if (appData.calendar) {
      const dates = Object.keys(appData.calendar).sort().reverse();
      if (dates.length > 0) {
        const parts = dates[0].split('-');
        if (parts.length === 3) {
          currentYear = parseInt(parts[0], 10);
          currentMonth = parseInt(parts[1], 10) - 1;
        }
        selectedDateStr = dates[0];
      }
      renderCalendar();
      if (selectedDateStr) renderSelectedDateDetails(selectedDateStr);
    }

    setupEventListeners();
  } catch (err) {
    console.error(err);
    categoryTableBody.innerHTML = `<tr><td colspan="12" class="empty-msg">Failed to load screener data. Please check connection.</td></tr>`;
  }
}

// Populate Top KPI Cards & Badges
function populateKPIs() {
  if (!appData || !appData.summary) return;

  const sum = appData.summary;
  kpiNewCount.textContent = sum.new_count || 0;
  kpiLatestDateLabel.textContent = `Latest EP Session: ${appData.latest_ep_date || 'N/A'}`;

  kpiPersistentCount.textContent = sum.persistent_count || 0;

  kpiSustainedRate.textContent = `${sum.sustained_rate_pct || 0}%`;
  kpiSustainedCountSub.textContent = `${sum.sustained_count || 0} stocks holding above EP1 Close`;

  kpiFizzledRate.textContent = `${sum.fizzled_rate_pct || 0}%`;
  kpiFizzledCountSub.textContent = `${sum.fizzled_count || 0} stocks lost 100% of EP1 gains`;

  badgeNewCount.textContent = sum.new_count || 0;
  badgePersistentCount.textContent = sum.persistent_count || 0;
  badgeSustainedCount.textContent = sum.sustained_count || 0;
  badgeFizzledCount.textContent = sum.fizzled_count || 0;
}

// Switch Main View (4-Category Analysis vs Calendar Explorer)
function switchMainView(viewName) {
  currentView = viewName;
  if (viewName === 'categories') {
    btnViewCategories.classList.add('active');
    btnViewCalendar.classList.remove('active');
    sectionCategories.classList.add('active');
    sectionCalendar.classList.remove('active');
  } else {
    btnViewCalendar.classList.add('active');
    btnViewCategories.classList.remove('active');
    sectionCalendar.classList.add('active');
    sectionCategories.classList.remove('active');
    renderCalendar();
    if (selectedDateStr) renderSelectedDateDetails(selectedDateStr);
  }
}

// Switch Active Category (New, Persistent, Sustained, Fizzled)
function switchCategory(catKey) {
  currentCategory = catKey;
  catTabBtns.forEach(btn => {
    if (btn.getAttribute('data-category') === catKey) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  const meta = CATEGORY_META[catKey];
  bannerIcon.textContent = meta.icon;
  bannerTitle.textContent = meta.title;
  bannerDesc.textContent = meta.desc;

  renderCategoryTable();
}

// Render the Active 4-Category Table with Tailored Column Headers
function renderCategoryTable() {
  if (!appData || !appData.tables) return;

  const rawList = appData.tables[currentCategory] || [];
  let list = rawList;

  // Filter with Category Search
  if (categorySearchQuery.trim() !== '') {
    const q = categorySearchQuery.toLowerCase();
    list = list.filter(item => item.symbol.toLowerCase().includes(q));
  }

  // 1. Render Table Headers based on category
  if (currentCategory === 'new_eps') {
    categoryTableHead.innerHTML = `
      <tr>
        <th>Symbol</th>
        <th>EP Date</th>
        <th>EP Close (₹)</th>
        <th>Change %</th>
        <th>Vol Ratio</th>
        <th>Volume</th>
        <th>50-SMA Vol</th>
        <th>Delivery %</th>
        <th>Breakout Type</th>
        <th>D+1 Status</th>
        <th>Action</th>
      </tr>
    `;
  } else if (currentCategory === 'persistent_eps') {
    categoryTableHead.innerHTML = `
      <tr>
        <th>Symbol</th>
        <th>50d EP Hits</th>
        <th>1st EP Date</th>
        <th>Latest EP Date</th>
        <th>1st EP Close (₹)</th>
        <th>Latest EP Close (₹)</th>
        <th>Gain Since EP1 %</th>
        <th>Delivery Trend</th>
        <th>Action</th>
      </tr>
    `;
  } else if (currentCategory === 'sustained_eps') {
    categoryTableHead.innerHTML = `
      <tr>
        <th>Symbol</th>
        <th>1st EP Date</th>
        <th>1st EP Close (₹)</th>
        <th>Current Price (₹)</th>
        <th>Gain Retained %</th>
        <th>Peak High (₹)</th>
        <th>Days Active</th>
        <th>Status</th>
        <th>Action</th>
      </tr>
    `;
  } else if (currentCategory === 'fizzled_eps') {
    categoryTableHead.innerHTML = `
      <tr>
        <th>Symbol</th>
        <th>1st EP Date</th>
        <th>Base Price (₹)</th>
        <th>1st EP Close (₹)</th>
        <th>Current Price (₹)</th>
        <th>Gain Lost %</th>
        <th>Net Loss vs Base %</th>
        <th>Status</th>
        <th>Action</th>
      </tr>
    `;
  }

  // 2. Render Table Rows
  if (list.length === 0) {
    categoryTableBody.innerHTML = `<tr><td colspan="11" class="empty-msg">No stocks found in ${CATEGORY_META[currentCategory].title}.</td></tr>`;
    return;
  }

  categoryTableBody.innerHTML = list.map((item, idx) => {
    if (currentCategory === 'new_eps') {
      const statusBadge = `badge-${(item.d1_status_latest || 'PENDING').toLowerCase()}`;
      const breakoutTypeHtml = item.appearance_count === 1
        ? `<span class="badge" style="background-color: rgba(56, 189, 248, 0.15); color: var(--accent-blue); border: 1px solid rgba(56, 189, 248, 0.3);">🌟 Fresh (1st Hit)</span>`
        : `<span class="badge" style="background-color: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3);">🔁 Repeat (${item.appearance_count}x)</span>`;

      return `
        <tr class="stock-row">
          <td class="symbol-cell">${item.symbol}</td>
          <td>${item.latest_ep_date}</td>
          <td style="font-weight: 700;">₹${item.latest_ep_close.toFixed(2)}</td>
          <td style="color: var(--accent-green); font-weight: 700;">+${item.latest_ep_change_pct}%</td>
          <td style="color: var(--accent-blue); font-weight: 700;">${item.latest_ep_vol_ratio}x</td>
          <td>${item.ep1_volume ? item.ep1_volume.toLocaleString('en-IN') : 'N/A'}</td>
          <td>${item.ep1_sma_vol ? Math.round(item.ep1_sma_vol).toLocaleString('en-IN') : 'N/A'}</td>
          <td>${item.ep1_deliv_per ? `${item.ep1_deliv_per}%` : 'N/A'}</td>
          <td>${breakoutTypeHtml}</td>
          <td><span class="badge ${statusBadge}">${item.d1_status_latest || 'PENDING'}</span></td>
          <td><button class="view-btn" onclick="openCategoryStockModal('${item.symbol}')">Details 🔍</button></td>
        </tr>
      `;
    } else if (currentCategory === 'persistent_eps') {
      const gainClass = item.current_return_since_ep1_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
      return `
        <tr class="stock-row">
          <td class="symbol-cell">${item.symbol}</td>
          <td><span class="badge" style="background-color: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7;">${item.appearance_count}x Hits</span></td>
          <td>${item.ep1_date}</td>
          <td>${item.latest_ep_date}</td>
          <td>₹${item.ep1_close.toFixed(2)}</td>
          <td style="font-weight: 700;">₹${item.latest_ep_close.toFixed(2)}</td>
          <td style="font-weight: 700; color: ${gainClass};">${item.current_return_since_ep1_pct > 0 ? '+' : ''}${item.current_return_since_ep1_pct}%</td>
          <td><span class="badge badge-${item.latest_deliv_trend.toLowerCase()}">${item.latest_deliv_trend}</span></td>
          <td><button class="view-btn" onclick="openCategoryStockModal('${item.symbol}')">Details 🔍</button></td>
        </tr>
      `;
    } else if (currentCategory === 'sustained_eps') {
      return `
        <tr class="stock-row">
          <td class="symbol-cell">${item.symbol}</td>
          <td>${item.ep1_date}</td>
          <td>₹${item.ep1_close.toFixed(2)}</td>
          <td style="font-weight: 700; color: var(--accent-green);">₹${item.current_price.toFixed(2)}</td>
          <td style="font-weight: 700; color: var(--accent-green);">+${item.retained_ep1_gain_pct}%</td>
          <td style="color: var(--accent-blue);">₹${item.max_high_since_ep1.toFixed(2)}</td>
          <td>${item.days_since_ep1} Sessions</td>
          <td><span class="badge badge-green">🟢 Holding Gain</span></td>
          <td><button class="view-btn" onclick="openCategoryStockModal('${item.symbol}')">Details 🔍</button></td>
        </tr>
      `;
    } else if (currentCategory === 'fizzled_eps') {
      const netLossPct = item.ep1_prev > 0 ? (((item.current_price - item.ep1_prev) / item.ep1_prev) * 100).toFixed(2) : '0';
      return `
        <tr class="stock-row">
          <td class="symbol-cell">${item.symbol}</td>
          <td>${item.ep1_date}</td>
          <td>₹${item.ep1_prev.toFixed(2)}</td>
          <td>₹${item.ep1_close.toFixed(2)}</td>
          <td style="font-weight: 700; color: var(--accent-red);">₹${item.current_price.toFixed(2)}</td>
          <td style="font-weight: 700; color: var(--accent-red);">${item.gain_lost_pct}% Lost</td>
          <td style="font-weight: 700; color: var(--accent-red);">${netLossPct}%</td>
          <td><span class="badge badge-red">🔴 Fizzled Out</span></td>
          <td><button class="view-btn" onclick="openCategoryStockModal('${item.symbol}')">Details 🔍</button></td>
        </tr>
      `;
    }
  }).join('');
}

// Open Stock Details Modal for Any Category
function openCategoryStockModal(symbol) {
  if (!appData || !appData.tables) return;
  
  // Search across all tables for this symbol
  let record = null;
  for (const cat of ['new_eps', 'persistent_eps', 'sustained_eps', 'fizzled_eps']) {
    const found = appData.tables[cat].find(x => x.symbol === symbol);
    if (found) {
      record = found;
      break;
    }
  }
  if (!record) return;

  document.getElementById('modal-symbol').textContent = record.symbol;
  
  const statusBadge = document.getElementById('modal-status-badge');
  if (record.current_price >= record.ep1_close) {
    statusBadge.textContent = 'SUSTAINED LEADER';
    statusBadge.className = 'badge badge-green';
  } else if (record.current_price < record.ep1_prev) {
    statusBadge.textContent = 'FIZZLED OUT';
    statusBadge.className = 'badge badge-red';
  } else {
    statusBadge.textContent = 'CONSOLIDATING';
    statusBadge.className = 'badge badge-yellow';
  }

  // 1st EP Day Details
  document.getElementById('m-ep-date').textContent = record.ep1_date;
  document.getElementById('m-ep-close').textContent = `₹${record.ep1_close.toFixed(2)}`;
  document.getElementById('m-ep-prev').textContent = `₹${record.ep1_prev.toFixed(2)}`;
  document.getElementById('m-ep-change').textContent = `+${record.ep1_change_pct}%`;
  document.getElementById('m-ep-vol').textContent = record.ep1_volume ? record.ep1_volume.toLocaleString('en-IN') : 'N/A';
  document.getElementById('m-ep-smavol').textContent = record.ep1_sma_vol ? Math.round(record.ep1_sma_vol).toLocaleString('en-IN') : 'N/A';
  document.getElementById('m-ep-volratio').textContent = `${record.ep1_vol_ratio}x Avg Vol`;
  document.getElementById('m-ep-ohl').textContent = `O: ₹${record.ep1_open.toFixed(2)} | H: ₹${record.ep1_high.toFixed(2)} | L: ₹${record.ep1_low.toFixed(2)}`;
  document.getElementById('m-ep-deliv').textContent = record.ep1_deliv_per ? `${record.ep1_deliv_per}%` : 'N/A';

  // 50-Day Subsequent Performance
  document.getElementById('m-current-price').textContent = `₹${record.current_price.toFixed(2)}`;
  document.getElementById('m-return-since-ep1').textContent = `${record.current_return_since_ep1_pct > 0 ? '+' : ''}${record.current_return_since_ep1_pct}%`;
  document.getElementById('m-return-since-ep1').style.color = record.current_return_since_ep1_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  
  document.getElementById('m-retained-ep1').textContent = `${record.retained_ep1_gain_pct}% (${record.gain_lost_pct}% lost)`;
  document.getElementById('m-peak-high').textContent = `₹${record.max_high_since_ep1.toFixed(2)}`;
  document.getElementById('m-hits-count').textContent = `${record.appearance_count}x in 50 Days`;

  if (record.current_price >= record.ep1_close) {
    document.getElementById('m-classification-eval').textContent = '🟢 SUSTAINED: Holding gains above 1st EP close';
    document.getElementById('m-classification-eval').style.color = 'var(--accent-green)';
  } else if (record.current_price < record.ep1_prev) {
    document.getElementById('m-classification-eval').textContent = '🔴 FIZZLED OUT: Dropped below 1st EP starting base';
    document.getElementById('m-classification-eval').style.color = 'var(--accent-red)';
  } else {
    document.getElementById('m-classification-eval').textContent = '🟡 CONSOLIDATING: Moderate pullback within EP range';
    document.getElementById('m-classification-eval').style.color = 'var(--accent-yellow)';
  }

  // External Chart Links
  document.getElementById('tradingview-link').href = `https://www.tradingview.com/chart/?symbol=NSE:${record.symbol}`;
  document.getElementById('nse-link').href = `https://www.nseindia.com/get-quotes/equity?symbol=${record.symbol}`;

  document.getElementById('stock-modal').classList.add('active');
}

// ─── CALENDAR LOGIC ───
function renderCalendar() {
  if (!appData || !appData.calendar) return;

  currentMonthLabel.textContent = `${MONTH_NAMES[currentMonth]} ${currentYear}`;
  calendarDaysGrid.innerHTML = '';

  const firstDayOfMonth = new Date(currentYear, currentMonth, 1);
  const lastDayOfMonth = new Date(currentYear, currentMonth + 1, 0);
  
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

// Render Selected Date Details in Calendar View
function renderSelectedDateDetails(dateStr) {
  const dayData = appData.calendar[dateStr];

  if (!dayData || dayData.count === 0) {
    selectedDateHeading.textContent = `No Episodic Pivots on ${dateStr}`;
    selectedDateSubheading.textContent = 'No stocks met the breakout criteria on this trading day.';
    epTableBody.innerHTML = `<tr><td colspan="12" class="empty-msg">No Episodic Pivots recorded for ${dateStr}.</td></tr>`;
    return;
  }

  let epList = dayData.ep_list;

  if (currentFilter !== 'ALL') {
    epList = epList.filter(ep => ep.d1_status === currentFilter);
  }

  if (calendarSearchQuery.trim() !== '') {
    epList = epList.filter(ep => ep.symbol.toLowerCase().includes(calendarSearchQuery.toLowerCase()));
  }

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
        <td><button class="view-btn" onclick="openCategoryStockModal('${ep.symbol}')">Details 🔍</button></td>
      </tr>
    `;
  }).join('');
}

function closeStockModal() {
  document.getElementById('stock-modal').classList.remove('active');
}

// Setup Event Listeners
function setupEventListeners() {
  // Main View Switcher
  btnViewCategories.addEventListener('click', () => switchMainView('categories'));
  btnViewCalendar.addEventListener('click', () => switchMainView('calendar'));

  // Category Tab Buttons
  catTabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const cat = btn.getAttribute('data-category');
      switchCategory(cat);
    });
  });

  // Category Search
  categorySearchInput.addEventListener('input', (e) => {
    categorySearchQuery = e.target.value;
    renderCategoryTable();
  });

  // Calendar Controls
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
      const parts = dates[0].split('-');
      if (parts.length === 3) {
        currentYear = parseInt(parts[0], 10);
        currentMonth = parseInt(parts[1], 10) - 1;
      }
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
    calendarSearchQuery = e.target.value;
    if (selectedDateStr) renderSelectedDateDetails(selectedDateStr);
  });

  document.getElementById('modal-close-btn').addEventListener('click', closeStockModal);
  document.getElementById('stock-modal').addEventListener('click', (e) => {
    if (e.target.id === 'stock-modal') closeStockModal();
  });
}

// Launch on DOM ready
document.addEventListener('DOMContentLoaded', initApp);

