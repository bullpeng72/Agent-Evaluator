/**
 * Agent Evaluator Documentation - Sidebar Navigation Script
 * Version: 1.0
 * Handles sidebar toggle, category collapse, active link highlighting, and search
 */

(function() {
    'use strict';

    // ============================================
    // Configuration
    // ============================================

    const CONFIG = {
        sidebarId: 'sidebar',
        toggleButtonId: 'sidebar-toggle',
        mainContentId: 'main-content',
        searchInputId: 'doc-search',
        categoryHeaderClass: 'category-header',
        categoryItemsClass: 'category-items',
        activeClass: 'active',
        collapsedClass: 'collapsed',
        openClass: 'open',
        storageKey: 'agent-evaluator-sidebar-state'
    };

    // ============================================
    // DOM Elements
    // ============================================

    const sidebar = document.getElementById(CONFIG.sidebarId);
    const toggleButton = document.getElementById(CONFIG.toggleButtonId);
    const mainContent = document.getElementById(CONFIG.mainContentId);
    const searchInput = document.getElementById(CONFIG.searchInputId);
    const categoryHeaders = document.querySelectorAll(`.${CONFIG.categoryHeaderClass}`);
    const navLinks = document.querySelectorAll('.category-items a');

    // ============================================
    // State Management
    // ============================================

    /**
     * Get current document filename
     */
    function getCurrentDocument() {
        const path = window.location.pathname;
        return path.substring(path.lastIndexOf('/') + 1);
    }

    /**
     * Load sidebar state from localStorage
     */
    function loadSidebarState() {
        try {
            const state = localStorage.getItem(CONFIG.storageKey);
            return state ? JSON.parse(state) : {};
        } catch (e) {
            console.error('Failed to load sidebar state:', e);
            return {};
        }
    }

    /**
     * Save sidebar state to localStorage
     */
    function saveSidebarState(state) {
        try {
            localStorage.setItem(CONFIG.storageKey, JSON.stringify(state));
        } catch (e) {
            console.error('Failed to save sidebar state:', e);
        }
    }

    // ============================================
    // Active Link Highlighting
    // ============================================

    /**
     * Highlight current document in sidebar
     */
    function highlightActiveLink() {
        const currentDoc = getCurrentDocument();

        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href === currentDoc || href === `./${currentDoc}`) {
                link.classList.add(CONFIG.activeClass);

                // Ensure parent category is expanded
                const categoryList = link.closest(`.${CONFIG.categoryItemsClass}`);
                if (categoryList) {
                    categoryList.classList.remove(CONFIG.collapsedClass);
                    categoryList.style.maxHeight = categoryList.scrollHeight + 'px';

                    const categoryHeader = categoryList.previousElementSibling;
                    if (categoryHeader) {
                        categoryHeader.classList.remove(CONFIG.collapsedClass);
                    }
                }
            } else {
                link.classList.remove(CONFIG.activeClass);
            }
        });
    }

    // ============================================
    // Category Collapse/Expand
    // ============================================

    /**
     * Toggle category expand/collapse
     */
    function toggleCategory(header) {
        const categoryId = header.getAttribute('data-category');
        const categoryList = document.querySelector(
            `.${CONFIG.categoryItemsClass}[data-category="${categoryId}"]`
        );

        if (!categoryList) return;

        const isCollapsed = header.classList.toggle(CONFIG.collapsedClass);

        if (isCollapsed) {
            categoryList.style.maxHeight = '0';
            categoryList.classList.add(CONFIG.collapsedClass);
        } else {
            categoryList.style.maxHeight = categoryList.scrollHeight + 'px';
            categoryList.classList.remove(CONFIG.collapsedClass);
        }

        // Save state
        const state = loadSidebarState();
        state[categoryId] = !isCollapsed;
        saveSidebarState(state);
    }

    /**
     * Initialize category states
     */
    function initializeCategoryStates() {
        const state = loadSidebarState();

        categoryHeaders.forEach(header => {
            const categoryId = header.getAttribute('data-category');
            const categoryList = document.querySelector(
                `.${CONFIG.categoryItemsClass}[data-category="${categoryId}"]`
            );

            if (!categoryList) return;

            // Default: expanded, unless saved as collapsed
            const isExpanded = state[categoryId] !== false;

            if (isExpanded) {
                header.classList.remove(CONFIG.collapsedClass);
                categoryList.classList.remove(CONFIG.collapsedClass);
                categoryList.style.maxHeight = categoryList.scrollHeight + 'px';
            } else {
                header.classList.add(CONFIG.collapsedClass);
                categoryList.classList.add(CONFIG.collapsedClass);
                categoryList.style.maxHeight = '0';
            }
        });
    }

    // ============================================
    // Sidebar Toggle (Mobile)
    // ============================================

    /**
     * Toggle sidebar visibility
     */
    function toggleSidebar() {
        if (!sidebar || !toggleButton) return;

        const isOpen = sidebar.classList.toggle(CONFIG.openClass);
        document.body.classList.toggle('sidebar-open', isOpen);

        // Update ARIA attributes
        toggleButton.setAttribute('aria-expanded', isOpen);
        sidebar.setAttribute('aria-hidden', !isOpen);
    }

    /**
     * Close sidebar when clicking outside (mobile)
     */
    function closeSidebarOnOutsideClick(event) {
        if (window.innerWidth > 768) return;

        const isClickInsideSidebar = sidebar && sidebar.contains(event.target);
        const isClickOnToggle = toggleButton && toggleButton.contains(event.target);

        if (!isClickInsideSidebar && !isClickOnToggle && sidebar.classList.contains(CONFIG.openClass)) {
            toggleSidebar();
        }
    }

    // ============================================
    // Search Functionality
    // ============================================

    /**
     * Filter navigation items based on search query
     */
    function handleSearch(query) {
        const searchTerm = query.toLowerCase().trim();

        navLinks.forEach(link => {
            const title = link.querySelector('.doc-title').textContent.toLowerCase();
            const number = link.querySelector('.doc-number').textContent.toLowerCase();
            const matches = title.includes(searchTerm) || number.includes(searchTerm);

            link.style.display = matches ? 'flex' : 'none';
        });

        // Show all categories if searching, hide empty ones
        categoryHeaders.forEach(header => {
            const categoryId = header.getAttribute('data-category');
            const categoryList = document.querySelector(
                `.${CONFIG.categoryItemsClass}[data-category="${categoryId}"]`
            );

            if (!categoryList) return;

            const visibleLinks = Array.from(categoryList.querySelectorAll('a'))
                .filter(link => link.style.display !== 'none');

            if (searchTerm === '') {
                // Reset to saved state
                header.style.display = 'flex';
                categoryList.style.display = 'block';
                initializeCategoryStates();
            } else {
                // Expand categories with results
                if (visibleLinks.length > 0) {
                    header.style.display = 'flex';
                    categoryList.style.display = 'block';
                    header.classList.remove(CONFIG.collapsedClass);
                    categoryList.classList.remove(CONFIG.collapsedClass);
                    categoryList.style.maxHeight = categoryList.scrollHeight + 'px';
                } else {
                    header.style.display = 'none';
                    categoryList.style.display = 'none';
                }
            }
        });
    }

    // ============================================
    // Keyboard Navigation
    // ============================================

    /**
     * Handle keyboard shortcuts
     */
    function handleKeyboardShortcuts(event) {
        // Ctrl/Cmd + K: Focus search
        if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
            event.preventDefault();
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
            }
        }

        // Escape: Close sidebar (mobile) or blur search
        if (event.key === 'Escape') {
            if (window.innerWidth <= 768 && sidebar.classList.contains(CONFIG.openClass)) {
                toggleSidebar();
            } else if (document.activeElement === searchInput) {
                searchInput.blur();
            }
        }
    }

    // ============================================
    // Event Listeners
    // ============================================

    /**
     * Initialize all event listeners
     */
    function initializeEventListeners() {
        // Category headers
        categoryHeaders.forEach(header => {
            header.addEventListener('click', () => toggleCategory(header));
        });

        // Sidebar toggle button
        if (toggleButton) {
            toggleButton.addEventListener('click', toggleSidebar);
        }

        // Close sidebar on outside click (mobile)
        document.addEventListener('click', closeSidebarOnOutsideClick);

        // Search input
        if (searchInput) {
            searchInput.addEventListener('input', (e) => handleSearch(e.target.value));
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', handleKeyboardShortcuts);

        // Update category max-heights on window resize
        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                document.querySelectorAll(`.${CONFIG.categoryItemsClass}:not(.${CONFIG.collapsedClass})`)
                    .forEach(list => {
                        list.style.maxHeight = list.scrollHeight + 'px';
                    });
            }, 250);
        });
    }

    // ============================================
    // Initialization
    // ============================================

    /**
     * Initialize sidebar navigation
     */
    function init() {
        // Set initial ARIA attributes
        if (toggleButton) {
            toggleButton.setAttribute('aria-expanded', 'false');
        }
        if (sidebar) {
            sidebar.setAttribute('aria-hidden', 'false');
        }

        // Initialize category states from localStorage
        initializeCategoryStates();

        // Highlight current document
        highlightActiveLink();

        // Set up event listeners
        initializeEventListeners();

        console.log('Sidebar navigation initialized');
    }

    // ============================================
    // Run on DOM ready
    // ============================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
