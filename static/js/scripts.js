// Custom JavaScript for Market-Viewr

document.addEventListener('DOMContentLoaded', function() {
    // Activate tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Add smooth scrolling
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Make tables sortable
    const tables = document.querySelectorAll('.table');
    tables.forEach(table => {
        const headers = table.querySelectorAll('th');
        headers.forEach((header, index) => {
            header.addEventListener('click', () => {
                sortTable(table, index);
            });
            header.style.cursor = 'pointer';
            header.setAttribute('data-bs-toggle', 'tooltip');
            header.setAttribute('title', 'Click to sort');
        });
    });
    
    // Initialize market page when needed
    if (document.getElementById('candlestick-chart')) {
        initMarketPage();
    }
});

// Function to sort tables
function sortTable(table, column) {
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const isNumeric = rows.length > 0 && !isNaN(parseFloat(rows[0].cells[column].textContent));
    const direction = table.getAttribute('data-sort-direction') === 'asc' ? -1 : 1;

    // Sort the rows
    rows.sort((a, b) => {
        let aValue = a.cells[column].textContent.trim();
        let bValue = b.cells[column].textContent.trim();

        if (isNumeric) {
            // Extract numbers only
            aValue = parseFloat(aValue.replace(/[^0-9.-]+/g, ''));
            bValue = parseFloat(bValue.replace(/[^0-9.-]+/g, ''));
            return direction * (aValue - bValue);
        } else {
            return direction * aValue.localeCompare(bValue);
        }
    });

    // Update the table
    const tbody = table.querySelector('tbody');
    rows.forEach(row => tbody.appendChild(row));

    // Toggle sort direction
    table.setAttribute('data-sort-direction', direction === 1 ? 'asc' : 'desc');
}

// Market page specific functions
// Initialize the market page when loaded
function initMarketPage() {
    // Get token symbol from meta tag or extract from URL
    const tokenMetaTag = document.querySelector('meta[name="token-symbol"]');
    let tokenSymbol;
    
    if (tokenMetaTag) {
        tokenSymbol = tokenMetaTag.getAttribute('content');
    } else {
        // Fallback: try to extract token from URL path
        const pathParts = window.location.pathname.split('/');
        const marketIndex = pathParts.indexOf('market');
        if (marketIndex !== -1 && pathParts.length > marketIndex + 1) {
            tokenSymbol = pathParts[marketIndex + 1];
        } else {
            console.error('Unable to determine token symbol');
            return; // Exit if we can't determine the token
        }
    }
    
    let currentTimespan = '30'; // Default to 30 days
    
    // Check for active timespan from buttons
    const activeTimespanButton = document.querySelector('.timespan-btn.active');
    if (activeTimespanButton) {
        currentTimespan = activeTimespanButton.getAttribute('data-timespan');
    }
    
    // Initialize chart
    loadCandlestickChart(tokenSymbol, currentTimespan);
    
    // Load full order book data
    loadOrderBook(tokenSymbol);
    
    // Set up event listeners for timespan buttons
    setupTimespanButtons(tokenSymbol);
    
    // Set up filter controls for order book
    setupFilterControls(tokenSymbol);
    
    // Set up theme toggle listener for chart
    setupThemeToggle();
}

// Load candlestick chart data from API
function loadCandlestickChart(token, timeframe) {
    fetch(`/api/chart/${token}/${timeframe}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(chartData => {
            // Plot the chart
            Plotly.newPlot('candlestick-chart', chartData.data, chartData.layout, {
                responsive: true
            });
            
            // Check theme and update chart
            const isDarkMode = document.documentElement.getAttribute('data-bs-theme') === 'dark';
            if (isDarkMode) {
                updateChartForDarkMode();
            }
        })
        .catch(error => {
            console.error('Error loading chart data:', error);
            // Show error message in chart container
            document.getElementById('candlestick-chart').innerHTML = `
                <div class="alert alert-warning">
                    Error loading chart data for ${token}.
                </div>
            `;
        });
}

// Global variable to track excluded accounts
let excludedAccounts = [];

// Load complete order book data
function loadOrderBook(token, excludeList = []) {
    // Build URL with excluded accounts if any
    let url = `/api/orderbook/${token}`;
    if (excludeList && excludeList.length > 0) {
        url += `?exclude=${excludeList.join(',')}`;
    }
    
    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Update buy and sell book tables with complete data
            updateOrderBook(data.buy_book, 'buy-book-table');
            updateOrderBook(data.sell_book, 'sell-book-table');
            
            // Update most active accounts list
            if (data.most_active_accounts) {
                updateActiveAccountsList(data.most_active_accounts, excludeList);
            }
        })
        .catch(error => {
            console.error('Error loading order book data:', error);
        });
}

// Update the most active accounts list
function updateActiveAccountsList(accounts, currentlyExcluded = []) {
    const container = document.getElementById('active-accounts-list');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (accounts && accounts.length > 0) {
        const ul = document.createElement('ul');
        ul.className = 'list-group';
        
        accounts.forEach(accountData => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center py-2';
            
            // Create account name with action buttons
            const accountSpan = document.createElement('span');
            accountSpan.textContent = accountData.account;
            
            // Create order count badge
            const countBadge = document.createElement('span');
            countBadge.className = 'badge bg-primary rounded-pill';
            countBadge.textContent = accountData.count;
            
            // Create filter button
            const filterBtn = document.createElement('button');
            filterBtn.className = 'btn btn-sm ms-2';
            filterBtn.setAttribute('title', 'Filter account');
            
            // Check if account is already excluded
            const isExcluded = currentlyExcluded.includes(accountData.account);
            if (isExcluded) {
                filterBtn.className += ' btn-success';
                filterBtn.innerHTML = '<i class="bi bi-plus-circle"></i>';
                filterBtn.setAttribute('title', 'Include account');
            } else {
                filterBtn.className += ' btn-outline-secondary';
                filterBtn.innerHTML = '<i class="bi bi-dash-circle"></i>';
                filterBtn.setAttribute('title', 'Exclude account');
            }
            
            // Add event listener to filter button
            filterBtn.addEventListener('click', function() {
                const token = getTokenFromPage();
                if (isExcluded) {
                    // Remove from excluded list
                    excludedAccounts = excludedAccounts.filter(a => a !== accountData.account);
                } else {
                    // Add to excluded list
                    if (!excludedAccounts.includes(accountData.account)) {
                        excludedAccounts.push(accountData.account);
                    }
                }
                
                // Update filter input field
                const filterInput = document.getElementById('account-filter');
                if (filterInput) {
                    filterInput.value = excludedAccounts.join(',');
                }
                
                // Reload order book with updated filters
                loadOrderBook(token, excludedAccounts);
            });
            
            // Create wrapper for badge and button
            const badgeWrapper = document.createElement('div');
            badgeWrapper.className = 'd-flex align-items-center';
            badgeWrapper.appendChild(countBadge);
            badgeWrapper.appendChild(filterBtn);
            
            li.appendChild(accountSpan);
            li.appendChild(badgeWrapper);
            ul.appendChild(li);
        });
        
        container.appendChild(ul);
    } else {
        container.innerHTML = '<div class="alert alert-info mt-2">No account data available</div>';
    }
}

// Initialize filter controls
function setupFilterControls(token) {
    // Toggle filter panel
    const toggleBtn = document.getElementById('toggle-filters');
    const filterControls = document.getElementById('filter-controls');
    
    if (toggleBtn && filterControls) {
        toggleBtn.addEventListener('click', function() {
            const isVisible = filterControls.style.display !== 'none';
            filterControls.style.display = isVisible ? 'none' : 'block';
            toggleBtn.innerHTML = isVisible ? 
                '<i class="bi bi-chevron-down"></i>' : 
                '<i class="bi bi-chevron-up"></i>';
        });
    }
    
    // Apply filters button
    const applyBtn = document.getElementById('apply-filters');
    const filterInput = document.getElementById('account-filter');
    
    if (applyBtn && filterInput) {
        applyBtn.addEventListener('click', function() {
            const accounts = filterInput.value.split(',')
                .map(acc => acc.trim())
                .filter(acc => acc.length > 0);
            
            excludedAccounts = accounts;
            loadOrderBook(token, accounts);
        });
    }
    
    // Clear filters button
    const clearBtn = document.getElementById('clear-filters');
    
    if (clearBtn && filterInput) {
        clearBtn.addEventListener('click', function() {
            filterInput.value = '';
            excludedAccounts = [];
            loadOrderBook(token, []);
        });
    }
}

// Helper function to get token symbol from page
function getTokenFromPage() {
    const tokenMetaTag = document.querySelector('meta[name="token-symbol"]');
    if (tokenMetaTag) {
        return tokenMetaTag.getAttribute('content');
    }
    
    // Fallback: extract from URL
    const pathParts = window.location.pathname.split('/');
    const marketIndex = pathParts.indexOf('market');
    if (marketIndex !== -1 && pathParts.length > marketIndex + 1) {
        return pathParts[marketIndex + 1];
    }
    
    return null;
}

// Update order book table with data
function updateOrderBook(orders, tableId) {
    const table = document.getElementById(tableId);
    if (!table) {
        console.error(`Table with ID "${tableId}" not found`);
        return;
    }
    
    const tableBody = table.querySelector('tbody');
    
    // If we can't find the tbody, log an error and return
    if (!tableBody) {
        console.error(`tbody not found in table with ID "${tableId}"`);
        return;
    }
    
    // Clear existing rows first
    tableBody.innerHTML = '';
    
    if (orders && orders.length > 0) {
        // Create rows for each order
        orders.forEach(order => {
            const quantity = parseFloat(order.quantity);
            const price = parseFloat(order.price);
            const total = quantity * price;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${order._id}</td>
                <td>${order.account}</td>
                <td>${quantity.toFixed(8)}</td>
                <td>${price.toFixed(8)}</td>
                <td>${total.toFixed(8)}</td>
            `;
            tableBody.appendChild(row);
        });
    } else {
        // Show no orders message
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="5" class="text-center">No orders available</td>';
        tableBody.appendChild(row);
    }
}

// Set up event listeners for timespan buttons
function setupTimespanButtons(token) {
    document.querySelectorAll('.timespan-btn').forEach(button => {
        button.addEventListener('click', function() {
            const timespan = this.getAttribute('data-timespan');
            
            // Don't reload if already on this timespan
            if (this.classList.contains('active')) return;
            
            // Update button states
            document.querySelectorAll('.timespan-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            this.classList.add('active');
            
            // Load chart with new timespan
            loadCandlestickChart(token, timespan);
        });
    });
}

// Set up theme toggle for chart
function setupThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('change', function() {
            const isDarkMode = this.checked;
            
            if (isDarkMode) {
                updateChartForDarkMode();
            } else {
                updateChartForLightMode();
            }
        });
    }
}

// Update chart for dark mode
function updateChartForDarkMode() {
    const chartElement = document.getElementById('candlestick-chart');
    if (!chartElement) return;
    
    // Update layout for dark mode
    Plotly.relayout('candlestick-chart', {
        'paper_bgcolor': '#212529',
        'plot_bgcolor': '#2c3034',
        'font.color': '#ffffff',
        'xaxis.gridcolor': '#495057',
        'xaxis.linecolor': '#6c757d',
        'xaxis.tickcolor': '#6c757d',
        'xaxis.tickfont.color': '#ffffff',
        'yaxis.gridcolor': '#495057',
        'yaxis.linecolor': '#6c757d',
        'yaxis.tickcolor': '#6c757d',
        'yaxis.tickfont.color': '#ffffff'
    });

    // Update candlestick colors for better visibility in dark mode
    const gd = chartElement;
    if (gd && gd.data) {
        for (let i = 0; i < gd.data.length; i++) {
            if (gd.data[i].type === 'candlestick') {
                Plotly.restyle('candlestick-chart', {
                    'increasing.line.color': '#00e676',
                    'increasing.fillcolor': '#00e676',
                    'decreasing.line.color': '#ff5252',
                    'decreasing.fillcolor': '#ff5252',
                    'line.width': 3
                }, [i]);
            }
        }
    }
}

// Update chart for light mode
function updateChartForLightMode() {
    const chartElement = document.getElementById('candlestick-chart');
    if (!chartElement) return;
    
    // Update layout for light mode
    Plotly.relayout('candlestick-chart', {
        'paper_bgcolor': '#ffffff',
        'plot_bgcolor': '#ffffff',
        'font.color': '#212529',
        'xaxis.gridcolor': '#e9ecef',
        'xaxis.linecolor': '#ced4da',
        'xaxis.tickcolor': '#ced4da',
        'xaxis.tickfont.color': '#212529',
        'yaxis.gridcolor': '#e9ecef',
        'yaxis.linecolor': '#ced4da',
        'yaxis.tickcolor': '#ced4da',
        'yaxis.tickfont.color': '#212529'
    });

    // Update candlestick colors for light mode
    const gd = chartElement;
    if (gd && gd.data) {
        for (let i = 0; i < gd.data.length; i++) {
            if (gd.data[i].type === 'candlestick') {
                Plotly.restyle('candlestick-chart', {
                    'increasing.line.color': '#26a69a',
                    'increasing.fillcolor': '#26a69a',
                    'decreasing.line.color': '#ef5350',
                    'decreasing.fillcolor': '#ef5350',
                    'line.width': 2
                }, [i]);
            }
        }
    }
}