// Custom JavaScript for Market-Viewr

document.addEventListener("DOMContentLoaded", function () {
  // Always reset the top load bar on fresh load
  resetTopLoadBar();
  // Activate tooltips
  const tooltipTriggerList = [].slice.call(
    document.querySelectorAll('[data-bs-toggle="tooltip"]'),
  );
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });

  // Add smooth scrolling
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      e.preventDefault();
      document.querySelector(this.getAttribute("href")).scrollIntoView({
        behavior: "smooth",
      });
    });
  });

  // Make tables sortable
  const tables = document.querySelectorAll(".table");
  tables.forEach((table) => {
    // Skip order book tables
    if (table.id === "buy-book-table" || table.id === "sell-book-table") {
      return;
    }
    const headers = table.querySelectorAll("th");
    headers.forEach((header, index) => {
      header.addEventListener("click", function () {
        sortTable(table, index);
      });
      header.style.cursor = "pointer";
      header.setAttribute("data-bs-toggle", "tooltip");
      header.setAttribute("title", "Click to sort");
    });
  });

  // Initialize market page when needed
  if (document.getElementById("candlestick-chart")) {
    initMarketPage();
  }

  // Initialize lazy loading for token icons
  initLazyTokenIcons();

  // Initialize action button loading states (top load bar)
  initActionButtonLoading();
});

// Also handle back/forward cache restores and tab visibility changes
window.addEventListener('pageshow', function(event) {
  // When navigating back/forward, ensure the bar isn't stuck
  resetTopLoadBar();
});

document.addEventListener('visibilitychange', function() {
  if (document.visibilityState === 'visible') {
    resetTopLoadBar();
  }
});

// Function to sort tables
function sortTable(table, column, forcedDirection = null) {
  const rows = Array.from(table.querySelectorAll("tbody tr"));

  // Use forced direction if provided, otherwise toggle
  let direction;
  if (forcedDirection) {
    direction = forcedDirection === "asc" ? 1 : -1;
  } else {
    direction = table.getAttribute("data-sort-direction") === "asc" ? -1 : 1;
  }

  // Sort the rows
  rows.sort((a, b) => {
    // Skip rows with colspans (like 'No orders available')
    if (a.querySelector("td[colspan]") || b.querySelector("td[colspan]")) {
      return 0;
    }

    const cellA = a.querySelectorAll("td")[column];
    const cellB = b.querySelectorAll("td")[column];

    if (!cellA || !cellB) return 0;

    let valueA = cellA.textContent.trim();
    let valueB = cellB.textContent.trim();

    // Attempt to parse YYYY-MM-DD HH:MM:SS or ISO date strings first
    const parseDateValue = (str) => {
      const isoLike = str.trim().replace(' ', 'T');
      return Date.parse(isoLike);
    };
    const dateA = parseDateValue(valueA);
    const dateB = parseDateValue(valueB);
    if (!isNaN(dateA) && !isNaN(dateB)) {
      return direction * (dateA - dateB);
    }

    // Check if the values are numbers AFTER trying dates
    const numA = parseFloat(valueA.replace(/,/g, ""));
    const numB = parseFloat(valueB.replace(/,/g, ""));
    if (!isNaN(numA) && !isNaN(numB)) {
      return direction * (numA - numB);
    }


    // Otherwise sort as strings
    return direction * valueA.localeCompare(valueB);
  });

  // Update the table
  const tbody = table.querySelector("tbody");
  rows.forEach((row) => tbody.appendChild(row));

  // Set the direction attribute
  table.setAttribute("data-sort-direction", direction === 1 ? "asc" : "desc");

  // Update sort indicators
  const headers = table.querySelectorAll("th");
  headers.forEach((header, index) => {
    // Remove any existing indicators
    header.classList.remove("sorted-asc", "sorted-desc");

    // Add indicator to the sorted column
    if (index === column) {
      header.classList.add(direction === 1 ? "sorted-asc" : "sorted-desc");
    }
  });
}

// Market page specific functions
// Initialize the market page when loaded
function initMarketPage() {
  // Get token symbol from meta tag or extract from URL
  const tokenMetaTag = document.querySelector('meta[name="token-symbol"]');
  let tokenSymbol;

  if (tokenMetaTag) {
    tokenSymbol = tokenMetaTag.getAttribute("content");
  } else {
    // Fallback: try to extract token from URL path
    const pathParts = window.location.pathname.split("/");
    const marketIndex = pathParts.indexOf("market");
    if (marketIndex !== -1 && pathParts.length > marketIndex + 1) {
      tokenSymbol = pathParts[marketIndex + 1];
    } else {
      console.error("Unable to determine token symbol");
      return; // Exit if we can't determine the token
    }
  }

  let currentTimespan = "30"; // Default to 30 days

  // Check for active timespan from buttons
  const activeTimespanButton = document.querySelector(".timespan-btn.active");
  if (activeTimespanButton) {
    currentTimespan = activeTimespanButton.getAttribute("data-timespan");
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
    .then((response) => {
      if (!response.ok) {
        throw new Error("Network response was not ok");
      }
      return response.json();
    })
    .then((chartData) => {
      // Plot the chart
      Plotly.newPlot("candlestick-chart", chartData.data, chartData.layout, {
        responsive: true,
      });

      // Check theme and update chart
      const isDarkMode =
        document.documentElement.getAttribute("data-bs-theme") === "dark";
      if (isDarkMode) {
        updateChartForDarkMode();
      }
    })
    .catch((error) => {
      console.error("Error loading chart data:", error);
      // Show error message in chart container
      document.getElementById("candlestick-chart").innerHTML = `
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
    url += `?exclude=${excludeList.join(",")}`;
  }

  fetch(url)
    .then((response) => {
      if (!response.ok) {
        throw new Error("Network response was not ok");
      }
      return response.json();
    })
    .then((data) => {
      // Update buy and sell book tables with complete data
      updateOrderBook(data.buy_book, "buy-book-table");
      updateOrderBook(data.sell_book, "sell-book-table");

      // Ensure tables maintain their formatting
      ensureTableFormatting();

      // Update most active accounts list
      if (data.most_active_accounts) {
        updateActiveAccountsList(data.most_active_accounts, excludeList);
      }
    })
    .catch((error) => {
      console.error("Error loading order book data:", error);
    });
}

// Ensure tables maintain their formatting
function ensureTableFormatting() {
  // Format buy book table
  document
    .querySelectorAll(
      "#buy-book-table td:nth-child(3):not([colspan]), #buy-book-table td:nth-child(4):not([colspan]), #buy-book-table td:nth-child(5):not([colspan])",
    )
    .forEach((cell) => {
      cell.classList.add("number-cell", "text-end");
    });

  // Format sell book table
  document
    .querySelectorAll(
      "#sell-book-table td:nth-child(1):not([colspan]), #sell-book-table td:nth-child(2):not([colspan]), #sell-book-table td:nth-child(3):not([colspan])",
    )
    .forEach((cell) => {
      cell.classList.add("number-cell", "text-end");
    });

  // Make sure price columns have the right classes
  document
    .querySelectorAll("#buy-book-table td:nth-child(5):not([colspan])")
    .forEach((cell) => {
      cell.classList.add("price-column", "text-success", "fw-bold");
    });

  document
    .querySelectorAll("#sell-book-table td:nth-child(1):not([colspan])")
    .forEach((cell) => {
      cell.classList.add("price-column", "text-danger", "fw-bold");
    });

  // Format trade history table
  document
    .querySelectorAll(
      "#trade-history-table td:nth-child(5), #trade-history-table td:nth-child(6), #trade-history-table td:nth-child(7)",
    )
    .forEach((cell) => {
      cell.classList.add("number-cell", "text-end");
    });

  // Add sorting functionality to table headers if not already present
  ["buy-book-table", "sell-book-table", "trade-history-table"].forEach(
    (tableId) => {
      const table = document.getElementById(tableId);
      if (table && !table.hasAttribute("data-sort-initialized")) {
        table.setAttribute("data-sort-initialized", "true");
        table.setAttribute("data-sort-direction", "asc");

        const headers = table.querySelectorAll("th");
        headers.forEach((header, index) => {
          header.style.cursor = "pointer";
          header.setAttribute("title", "Click to sort");
          header.addEventListener("click", function () {
            sortTable(table, index);
          });
        });
      }
    },
  );
}

// Lazy-load token icons with timeout and error fallback
function initLazyTokenIcons() {
  const images = document.querySelectorAll("img.token-icon");
  if (!images || images.length === 0) return;

  const placeholder = "/static/images/coin-placeholder.svg";

  const loadImg = (img) => {
    const actualSrc = img.getAttribute("data-src");
    if (!actualSrc) return; // Keep placeholder if no real src

    // Prevent duplicate loads
    if (img.dataset.loaded === "true") return;
    img.dataset.loaded = "true";

    // Fallback on error
    img.onerror = function () {
      if (img.src !== placeholder) img.src = placeholder;
    };

    // Short timeout fallback
    const TIMEOUT_MS = 2500;
    const timer = setTimeout(() => {
      if (img.src !== placeholder) img.src = placeholder;
    }, TIMEOUT_MS);

    img.onload = function () {
      clearTimeout(timer);
    };

    // Trigger actual load
    img.src = actualSrc;
  };

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const img = entry.target;
            loadImg(img);
            obs.unobserve(img);
          }
        });
      },
      { root: null, rootMargin: "200px", threshold: 0.01 },
    );

    images.forEach((img) => observer.observe(img));
  } else {
    // Fallback: load immediately
    images.forEach((img) => loadImg(img));
  }
}

// Initialize loading states for action buttons (Market/Info)
function initActionButtonLoading() {
  const actionButtons = document.querySelectorAll('a.action-btn');
  if (actionButtons.length === 0) return;

  actionButtons.forEach((button) => {
    button.addEventListener('click', function () {
      startTopLoadBar();
    });
  });
}

// Top page load bar logic
let loadBarTimer = null;
function startTopLoadBar() {
  const bar = document.getElementById('page-load-bar');
  if (!bar) return;

  // Reset
  bar.style.transition = 'none';
  bar.style.width = '0%';
  // Kick in
  requestAnimationFrame(() => {
    bar.style.transition = 'width 0.3s ease';
    bar.style.width = '25%';
  });

  // Gradually progress while the next page is loading
  let progress = 25;
  clearInterval(loadBarTimer);
  loadBarTimer = setInterval(() => {
    progress = Math.min(progress + Math.random() * 15, 85);
    bar.style.width = progress + '%';
  }, 300);
}

function finishTopLoadBar() {
  const bar = document.getElementById('page-load-bar');
  if (!bar) return;
  clearInterval(loadBarTimer);
  bar.style.width = '100%';
  setTimeout(() => {
    bar.style.transition = 'width 0.2s ease';
    bar.style.width = '0%';
  }, 150);
}

function resetTopLoadBar() {
  const bar = document.getElementById('page-load-bar');
  if (!bar) return;
  clearInterval(loadBarTimer);
  bar.style.transition = 'none';
  bar.style.width = '0%';
}

// Update the most active accounts list
function updateActiveAccountsList(accounts, currentlyExcluded = []) {
  const container = document.getElementById("active-accounts-list");
  if (!container) return;

  container.innerHTML = "";

  if (accounts && accounts.length > 0) {
    const ul = document.createElement("ul");
    ul.className = "list-group";

    accounts.forEach((accountData) => {
      const li = document.createElement("li");
      li.className =
        "list-group-item d-flex justify-content-between align-items-center py-2";

      // Create account name with action buttons
      const accountSpan = document.createElement("span");
      accountSpan.textContent = accountData.account;

      // Create order count badge
      const countBadge = document.createElement("span");
      countBadge.className = "badge bg-primary rounded-pill";
      countBadge.textContent = accountData.count;

      // Create filter button
      const filterBtn = document.createElement("button");
      filterBtn.className = "btn btn-sm ms-2";
      filterBtn.setAttribute("title", "Filter account");

      // Check if account is already excluded
      const isExcluded = currentlyExcluded.includes(accountData.account);
      if (isExcluded) {
        filterBtn.className += " btn-success";
        filterBtn.innerHTML = '<i class="bi bi-plus-circle"></i>';
        filterBtn.setAttribute("title", "Include account");
      } else {
        filterBtn.className += " btn-outline-secondary";
        filterBtn.innerHTML = '<i class="bi bi-dash-circle"></i>';
        filterBtn.setAttribute("title", "Exclude account");
      }

      // Add event listener to filter button
      filterBtn.addEventListener("click", function () {
        const token = getTokenFromPage();
        if (isExcluded) {
          // Remove from excluded list
          excludedAccounts = excludedAccounts.filter(
            (a) => a !== accountData.account,
          );
        } else {
          // Add to excluded list
          if (!excludedAccounts.includes(accountData.account)) {
            excludedAccounts.push(accountData.account);
          }
        }

        // Update filter input field
        const filterInput = document.getElementById("account-filter");
        if (filterInput) {
          filterInput.value = excludedAccounts.join(",");
        }

        // Reload order book with updated filters
        loadOrderBook(token, excludedAccounts);
      });

      // Create wrapper for badge and button
      const badgeWrapper = document.createElement("div");
      badgeWrapper.className = "d-flex align-items-center";
      badgeWrapper.appendChild(countBadge);
      badgeWrapper.appendChild(filterBtn);

      li.appendChild(accountSpan);
      li.appendChild(badgeWrapper);
      ul.appendChild(li);
    });

    container.appendChild(ul);
  } else {
    container.innerHTML =
      '<div class="alert alert-info mt-2">No account data available</div>';
  }
}

// Initialize filter controls
function setupFilterControls(token) {
  // Toggle filter panel
  const toggleBtn = document.getElementById("toggle-filters");
  const filterControls = document.getElementById("filter-controls");

  if (toggleBtn && filterControls) {
    toggleBtn.addEventListener("click", function () {
      const isVisible = filterControls.style.display !== "none";
      filterControls.style.display = isVisible ? "none" : "block";
      toggleBtn.innerHTML = isVisible
        ? '<i class="bi bi-chevron-down"></i>'
        : '<i class="bi bi-chevron-up"></i>';
    });
  }

  // Apply filters button
  const applyBtn = document.getElementById("apply-filters");
  const filterInput = document.getElementById("account-filter");

  if (applyBtn && filterInput) {
    applyBtn.addEventListener("click", function () {
      const accounts = filterInput.value
        .split(",")
        .map((acc) => acc.trim())
        .filter((acc) => acc.length > 0);

      excludedAccounts = accounts;
      loadOrderBook(token, accounts);
    });
  }

  // Clear filters button
  const clearBtn = document.getElementById("clear-filters");

  if (clearBtn && filterInput) {
    clearBtn.addEventListener("click", function () {
      filterInput.value = "";
      excludedAccounts = [];
      loadOrderBook(token, []);
    });
  }
}

// Helper function to get token symbol from page
function getTokenFromPage() {
  const tokenMetaTag = document.querySelector('meta[name="token-symbol"]');
  if (tokenMetaTag) {
    return tokenMetaTag.getAttribute("content");
  }

  // Fallback: extract from URL
  const pathParts = window.location.pathname.split("/");
  const marketIndex = pathParts.indexOf("market");
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

  const tableBody = table.querySelector("tbody");

  // If we can't find the tbody, log an error and return
  if (!tableBody) {
    console.error(`tbody not found in table with ID "${tableId}"`);
    return;
  }

  // Clear existing rows first
  tableBody.innerHTML = "";

  if (orders && orders.length > 0) {
    // Create rows for each order
    orders.forEach((order) => {
      const quantity = parseFloat(order.quantity);
      const price = parseFloat(order.price);
      const total = quantity * price;

      const row = document.createElement("tr");

      // Different layout for buy and sell tables
      if (tableId === "buy-book-table") {
        row.innerHTML = `
                    <td>${order._id}</td>
                    <td>${order.account}</td>
                    <td class="number-cell text-end">${quantity.toFixed(8)}</td>
                    <td class="number-cell text-end">${total.toFixed(8)}</td>
                    <td class="text-success fw-bold number-cell text-end price-column">${price.toFixed(8)}</td>
                `;
      } else if (tableId === "sell-book-table") {
        row.innerHTML = `
                    <td class="text-danger fw-bold number-cell text-end price-column">${price.toFixed(8)}</td>
                    <td class="number-cell text-end">${total.toFixed(8)}</td>
                    <td class="number-cell text-end">${quantity.toFixed(8)}</td>
                    <td>${order.account}</td>
                    <td>${order._id}</td>
                `;
      }

      tableBody.appendChild(row);
    });

    // Sort by price by default
    if (tableId === "buy-book-table") {
      // Sort buy orders by price (descending) - column index 4
      sortTable(table, 4, "desc");
    } else if (tableId === "sell-book-table") {
      // Sort sell orders by price (ascending) - column index 0
      sortTable(table, 0, "asc");
    }
  } else {
    // Show no orders message
    const row = document.createElement("tr");
    const colSpan = table.querySelector("thead tr").children.length || 5;
    row.innerHTML = `<td colspan="${colSpan}" class="text-center text-muted empty-state">No orders available</td>`;
    tableBody.appendChild(row);
  }

  // Ensure consistent formatting
  ensureTableFormatting();
}

// Set up event listeners for timespan buttons
function setupTimespanButtons(token) {
  document.querySelectorAll(".timespan-btn").forEach((button) => {
    button.addEventListener("click", function () {
      const timespan = this.getAttribute("data-timespan");

      // Don't reload if already on this timespan
      if (this.classList.contains("active")) return;

      // Update button states
      document.querySelectorAll(".timespan-btn").forEach((btn) => {
        btn.classList.remove("active");
      });
      this.classList.add("active");

      // Load chart with new timespan
      loadCandlestickChart(token, timespan);
    });
  });
}

// Set up theme toggle for chart
function setupThemeToggle() {
  const themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
    themeToggle.addEventListener("change", function () {
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
  const chartElement = document.getElementById("candlestick-chart");
  if (!chartElement) return;

  // Update layout for dark mode
  Plotly.relayout("candlestick-chart", {
    paper_bgcolor: "#212529",
    plot_bgcolor: "#2c3034",
    "font.color": "#ffffff",
    "xaxis.gridcolor": "#495057",
    "xaxis.linecolor": "#6c757d",
    "xaxis.tickcolor": "#6c757d",
    "xaxis.tickfont.color": "#ffffff",
    "yaxis.gridcolor": "#495057",
    "yaxis.linecolor": "#6c757d",
    "yaxis.tickcolor": "#6c757d",
    "yaxis.tickfont.color": "#ffffff",
  });

  // Update candlestick colors for better visibility in dark mode
  const gd = chartElement;
  if (gd && gd.data) {
    for (let i = 0; i < gd.data.length; i++) {
      if (gd.data[i].type === "candlestick") {
        Plotly.restyle(
          "candlestick-chart",
          {
            "increasing.line.color": "#00e676",
            "increasing.fillcolor": "#00e676",
            "decreasing.line.color": "#ff5252",
            "decreasing.fillcolor": "#ff5252",
            "line.width": 3,
          },
          [i],
        );
      }
    }
  }
}

// Update chart for light mode
function updateChartForLightMode() {
  const chartElement = document.getElementById("candlestick-chart");
  if (!chartElement) return;

  // Update layout for light mode
  Plotly.relayout("candlestick-chart", {
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    "font.color": "#212529",
    "xaxis.gridcolor": "#e9ecef",
    "xaxis.linecolor": "#ced4da",
    "xaxis.tickcolor": "#ced4da",
    "xaxis.tickfont.color": "#212529",
    "yaxis.gridcolor": "#e9ecef",
    "yaxis.linecolor": "#ced4da",
    "yaxis.tickcolor": "#ced4da",
    "yaxis.tickfont.color": "#212529",
  });

  // Update candlestick colors for light mode
  const gd = chartElement;
  if (gd && gd.data) {
    for (let i = 0; i < gd.data.length; i++) {
      if (gd.data[i].type === "candlestick") {
        Plotly.restyle(
          "candlestick-chart",
          {
            "increasing.line.color": "#26a69a",
            "increasing.fillcolor": "#26a69a",
            "decreasing.line.color": "#ef5350",
            "decreasing.fillcolor": "#ef5350",
            "line.width": 2,
          },
          [i],
        );
      }
    }
  }
}
