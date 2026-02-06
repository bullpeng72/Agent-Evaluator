/**
 * Agent Evaluator - iframe 문서 뷰어 스크립트
 * Sidebar 링크를 클릭하면 우측 iframe에 문서를 로드합니다.
 */

(function() {
    'use strict';

    // ============================================
    // Configuration
    // ============================================

    const CONFIG = {
        iframeId: 'doc-iframe',
        welcomeScreenId: 'welcome-screen',
        iframeHeaderId: 'iframe-header',
        docTitleId: 'doc-title',
        breadcrumbId: 'breadcrumb',
        loadingIndicatorId: 'loading-indicator',
        storageKey: 'agent-evaluator-current-doc'
    };

    // Document metadata mapping
    const DOC_METADATA = {
        'index_content.html': { title: 'Welcome', category: 'Home' },
        'GETTING_STARTED.html': { title: 'Getting Started', category: 'For Developers' },
        'DEVELOPER_QUICKSTART_GUIDE.html': { title: 'Developer Guide', category: 'For Developers' },
        'METRICS_GUIDE.html': { title: 'Metrics Guide', category: 'For Developers' },
        'FRAMEWORK_INTEGRATION.html': { title: 'Framework Integration', category: 'For Developers' },
        'API_REFERENCE.html': { title: 'API Reference', category: 'For Developers' },
        'DEPLOYMENT_GUIDE.html': { title: 'Deployment', category: 'For Developers' },
        'DASHBOARD.html': { title: 'Dashboard', category: 'For QA Engineers' },
        'DATA_EDITOR_TRANSPARENCY_GUIDE.html': { title: 'Data Editor', category: 'For QA Engineers' },
        'GOLDEN_DATASET_GUIDE.html': { title: 'Golden Dataset', category: 'For QA Engineers' },
        'THRESHOLD_CONFIGURATION_GUIDE.html': { title: 'Threshold Config', category: 'For QA Engineers' },
        'KOREAN_RAG_GUIDE.html': { title: 'Korean RAG', category: 'For QA Engineers' },
        'AGENTIC_AI_METRICS_GUIDE.html': { title: 'Agentic AI Metrics', category: 'References' },
        'LEARNING_GUIDE.html': { title: 'Learning Guide', category: 'References' },
        'README.html': { title: 'README', category: 'References' }
    };

    // Category name mapping
    const CATEGORY_NAMES = {
        'developers': '👨‍💻 For Developers',
        'qa': '🧪 For QA Engineers',
        'references': '📚 References',
        'home': 'Home'
    };

    // ============================================
    // DOM Elements
    // ============================================

    const iframe = document.getElementById(CONFIG.iframeId);
    const welcomeScreen = document.getElementById(CONFIG.welcomeScreenId);
    const iframeHeader = document.getElementById(CONFIG.iframeHeaderId);
    const docTitle = document.getElementById(CONFIG.docTitleId);
    const breadcrumb = document.getElementById(CONFIG.breadcrumbId);
    const loadingIndicator = document.getElementById(CONFIG.loadingIndicatorId);
    const navLinks = document.querySelectorAll('.category-items a');

    // ============================================
    // iframe Management
    // ============================================

    /**
     * Load a document into the iframe
     */
    function loadDocument(url, title, category) {
        console.log(`Loading document: ${url}`);

        // Show loading indicator
        showLoading();

        // Hide welcome screen
        if (welcomeScreen) {
            welcomeScreen.classList.add('hidden');
        }

        // Show iframe and header
        if (iframe) {
            iframe.style.display = 'block';
        }
        if (iframeHeader) {
            iframeHeader.style.display = 'flex';
        }

        // Update header title
        updateHeader(title, category);

        // Update breadcrumb
        updateBreadcrumb(category, title);

        // Load the document
        iframe.src = url;

        // Save current document
        saveCurrentDocument(url, title, category);
    }

    /**
     * Show loading indicator
     */
    function showLoading() {
        if (loadingIndicator) {
            loadingIndicator.classList.add('active');
        }
    }

    /**
     * Hide loading indicator
     */
    function hideLoading() {
        if (loadingIndicator) {
            loadingIndicator.classList.remove('active');
        }
    }

    /**
     * Update iframe header
     */
    function updateHeader(title, category) {
        if (docTitle) {
            docTitle.textContent = title;
        }
    }

    /**
     * Update breadcrumb navigation
     */
    function updateBreadcrumb(category, title) {
        if (!breadcrumb) return;

        breadcrumb.innerHTML = `
            <a href="#" onclick="window.location.reload(); return false;">Home</a>
            <span class="breadcrumb-separator">›</span>
            <span>${category}</span>
            <span class="breadcrumb-separator">›</span>
            <span class="breadcrumb-current">${title}</span>
        `;
    }

    /**
     * Save current document to localStorage
     */
    function saveCurrentDocument(url, title, category) {
        try {
            localStorage.setItem(CONFIG.storageKey, JSON.stringify({
                url, title, category, timestamp: Date.now()
            }));
        } catch (e) {
            console.error('Failed to save current document:', e);
        }
    }

    /**
     * Load last viewed document from localStorage
     */
    function loadLastDocument() {
        try {
            const saved = localStorage.getItem(CONFIG.storageKey);
            if (saved) {
                const { url, title, category } = JSON.parse(saved);
                loadDocument(url, title, category);
                return true;
            }
        } catch (e) {
            console.error('Failed to load last document:', e);
        }
        return false;
    }

    // ============================================
    // iframe Content Handling
    // ============================================

    /**
     * Handle iframe load event
     */
    function onIframeLoad() {
        hideLoading();

        try {
            // Try to access iframe content (same-origin only)
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            const iframeBody = iframeDoc.body;

            // Add class to indicate it's inside iframe
            if (iframeBody) {
                iframeBody.classList.add('in-iframe');
            }

            // Hide sidebar in iframe content
            hideSidebarInIframe(iframeDoc);

            console.log('Document loaded successfully');
        } catch (e) {
            // Cross-origin restrictions - can't access iframe content
            console.log('Cannot access iframe content (cross-origin)');
        }
    }

    /**
     * Hide sidebar in iframe content
     */
    function hideSidebarInIframe(iframeDoc) {
        try {
            // Hide sidebar
            const sidebar = iframeDoc.querySelector('#sidebar, .sidebar');
            if (sidebar) {
                sidebar.style.display = 'none';
            }

            // Hide toggle button
            const toggleButton = iframeDoc.querySelector('#sidebar-toggle, .sidebar-toggle');
            if (toggleButton) {
                toggleButton.style.display = 'none';
            }

            // Adjust main content margin
            const mainContent = iframeDoc.querySelector('#main-content, .main-content');
            if (mainContent) {
                mainContent.style.marginLeft = '0';
            }

            // Adjust body if it has flex display
            const body = iframeDoc.body;
            if (body) {
                const bodyDisplay = window.getComputedStyle(body).display;
                if (bodyDisplay === 'flex') {
                    body.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('Failed to hide sidebar in iframe:', e);
        }
    }

    // ============================================
    // Event Listeners
    // ============================================

    /**
     * Initialize navigation links
     */
    function initializeNavLinks() {
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();

                const href = link.getAttribute('href');
                const docName = link.querySelector('.doc-title')?.textContent || 'Document';

                // Get category from parent ul element's data-category attribute
                const parentUl = link.closest('ul[data-category]');
                const categoryKey = parentUl ? parentUl.getAttribute('data-category') : null;
                const categoryName = categoryKey ? CATEGORY_NAMES[categoryKey] : null;

                // Get metadata from DOC_METADATA or use link information
                const metadata = DOC_METADATA[href] || {
                    title: docName,
                    category: categoryName || 'Unknown'
                };

                // Use category from metadata if categoryName is not found
                const finalCategory = categoryName || metadata.category || 'Unknown';

                loadDocument(href, metadata.title, finalCategory);
            });
        });
    }

    /**
     * Initialize iframe load event
     */
    function initializeIframe() {
        if (iframe) {
            iframe.addEventListener('load', onIframeLoad);
        }
    }

    /**
     * Initialize open in new tab button
     */
    function initializeNewTabButton() {
        const newTabBtn = document.getElementById('open-new-tab-btn');
        if (newTabBtn && iframe) {
            newTabBtn.addEventListener('click', () => {
                const currentUrl = iframe.src;
                if (currentUrl && currentUrl !== 'about:blank') {
                    window.open(currentUrl, '_blank');
                }
            });
        }
    }

    /**
     * Initialize print button
     */
    function initializePrintButton() {
        const printBtn = document.getElementById('print-btn');
        if (printBtn && iframe) {
            printBtn.addEventListener('click', () => {
                try {
                    iframe.contentWindow.print();
                } catch (e) {
                    console.error('Failed to print iframe content:', e);
                    alert('Cannot print cross-origin content');
                }
            });
        }
    }

    // ============================================
    // Initialization
    // ============================================

    /**
     * Initialize iframe viewer
     */
    function init() {
        console.log('Initializing iframe viewer...');

        // Initialize iframe
        initializeIframe();

        // Initialize navigation links
        initializeNavLinks();

        // Initialize buttons
        initializeNewTabButton();
        initializePrintButton();

        // Try to load last viewed document
        const loaded = loadLastDocument();

        if (!loaded) {
            // Show welcome screen
            if (welcomeScreen) {
                welcomeScreen.classList.remove('hidden');
            }

            // Hide iframe and header initially
            if (iframe) {
                iframe.style.display = 'none';
            }
            if (iframeHeader) {
                iframeHeader.style.display = 'none';
            }
        }

        console.log('iframe viewer initialized');
    }

    // ============================================
    // Run on DOM ready
    // ============================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ============================================
    // Global functions (accessible from outside)
    // ============================================

    window.AgentEvaluatorViewer = {
        loadDocument: loadDocument,
        getCurrentDocument: () => {
            try {
                return JSON.parse(localStorage.getItem(CONFIG.storageKey));
            } catch (e) {
                return null;
            }
        }
    };

})();
