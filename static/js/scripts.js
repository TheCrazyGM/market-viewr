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