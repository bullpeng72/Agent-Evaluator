/**
 * Mermaid Diagram Zoom Functionality
 * Allows users to click on mermaid diagrams to view them in a modal with zoom
 */

(function() {
    'use strict';

    console.log('🔍 Mermaid Zoom: Script loaded');

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    function init() {
        console.log('🔍 Mermaid Zoom: Initializing...');

        // Wait for mermaid to be available and render
        waitForMermaid();
    }

    function waitForMermaid() {
        if (typeof mermaid === 'undefined') {
            console.warn('⚠️ Mermaid Zoom: Mermaid library not found, retrying...');
            setTimeout(waitForMermaid, 100);
            return;
        }

        console.log('✅ Mermaid Zoom: Mermaid library found');

        // Wait for diagrams to be rendered
        // Try multiple times with increasing delays
        const checkTimes = [500, 1000, 1500, 2000, 3000];
        let checkCount = 0;

        function checkDiagrams() {
            const svgs = document.querySelectorAll('svg[id^="mermaid-"], .mermaid svg');
            console.log(`🔍 Mermaid Zoom: Check #${checkCount + 1}, found ${svgs.length} SVG(s)`);

            if (svgs.length > 0) {
                addClickHandlers(svgs);
                setupMutationObserver();
                console.log('✅ Mermaid Zoom: Setup complete!');
            } else if (checkCount < checkTimes.length - 1) {
                checkCount++;
                setTimeout(checkDiagrams, checkTimes[checkCount] - checkTimes[checkCount - 1]);
            } else {
                console.warn('⚠️ Mermaid Zoom: No diagrams found after all retries');
            }
        }

        setTimeout(checkDiagrams, checkTimes[0]);
    }

    function setupMutationObserver() {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1) {
                        // Check if it's an SVG or contains SVGs
                        if (node.matches && node.matches('svg[id^="mermaid-"]')) {
                            console.log('🔍 Mermaid Zoom: New diagram detected via MutationObserver');
                            makeDiagramClickable(node);
                        } else if (node.querySelectorAll) {
                            const svgs = node.querySelectorAll('svg[id^="mermaid-"], .mermaid svg');
                            if (svgs.length > 0) {
                                console.log(`🔍 Mermaid Zoom: Found ${svgs.length} new diagram(s) via MutationObserver`);
                                addClickHandlers(svgs);
                            }
                        }
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        console.log('✅ Mermaid Zoom: MutationObserver started');
    }

    function addClickHandlers(svgs) {
        svgs.forEach((svg, index) => {
            makeDiagramClickable(svg);
        });
    }

    function makeDiagramClickable(svg) {
        // Skip if already clickable
        if (svg.classList.contains('mermaid-zoomable')) {
            return;
        }

        svg.classList.add('mermaid-zoomable');
        svg.style.cursor = 'pointer';
        svg.title = '클릭하여 확대';

        console.log('✅ Mermaid Zoom: Made diagram clickable', svg.id || '(no id)');

        svg.addEventListener('click', function(e) {
            console.log('🖱️ Mermaid Zoom: Diagram clicked!');
            e.preventDefault();
            e.stopPropagation();
            showZoomedDiagram(this);
        });
    }

    function showZoomedDiagram(svg) {
        console.log('📊 Mermaid Zoom: Opening modal...');

        // Check if modal already exists (should not happen)
        const existingModals = document.querySelectorAll('.mermaid-modal');
        if (existingModals.length > 0) {
            console.warn(`⚠️ Found ${existingModals.length} existing modal(s), removing them first`);
            existingModals.forEach(m => m.remove());
        }

        // Store original SVG dimensions before cloning
        const originalRect = svg.getBoundingClientRect();
        const originalWidth = originalRect.width;
        const originalHeight = originalRect.height;
        const originalAspectRatio = originalWidth / originalHeight;
        console.log(`📐 Original SVG size: ${originalWidth.toFixed(0)}x${originalHeight.toFixed(0)} (ratio: ${originalAspectRatio.toFixed(2)})`);

        // Clone SVG properly to avoid event listener issues
        const clonedSvg = svg.cloneNode(true);

        // Remove all event listeners and classes from cloned SVG
        clonedSvg.classList.remove('mermaid-zoomable');
        clonedSvg.removeAttribute('title');

        // Remove any onclick attributes
        clonedSvg.onclick = null;
        clonedSvg.removeAttribute('onclick');

        // Completely disable all pointer events on SVG and children
        // The modalBody will handle all drag events instead
        clonedSvg.style.pointerEvents = 'none';
        const allElements = clonedSvg.querySelectorAll('*');
        allElements.forEach(el => {
            el.style.pointerEvents = 'none';
            // Also remove any event attributes
            el.onclick = null;
            el.removeAttribute('onclick');
        });

        console.log(`🔒 Disabled pointer events on SVG and ${allElements.length} child elements`);

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'mermaid-modal';
        modal.innerHTML = `
            <div class="mermaid-modal-backdrop"></div>
            <div class="mermaid-modal-content">
                <div class="mermaid-modal-header">
                    <span class="mermaid-modal-title">다이어그램 확대 보기</span>
                    <div class="mermaid-modal-controls">
                        <button class="mermaid-btn mermaid-btn-zoom-in" title="확대 (Ctrl/Cmd + +)">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"></circle>
                                <line x1="11" y1="8" x2="11" y2="14"></line>
                                <line x1="8" y1="11" x2="14" y2="11"></line>
                                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                            </svg>
                        </button>
                        <button class="mermaid-btn mermaid-btn-zoom-out" title="축소 (Ctrl/Cmd + -)">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"></circle>
                                <line x1="8" y1="11" x2="14" y2="11"></line>
                                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                            </svg>
                        </button>
                        <button class="mermaid-btn mermaid-btn-reset" title="원본 크기 (Ctrl/Cmd + 0)">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                <circle cx="12" cy="12" r="3"></circle>
                            </svg>
                        </button>
                        <button class="mermaid-btn mermaid-btn-close" title="닫기 (ESC)">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="mermaid-modal-body">
                    <div class="mermaid-diagram-container">
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        console.log('✅ Mermaid Zoom: Modal added to DOM');

        // Get elements
        const modalContent = modal.querySelector('.mermaid-modal-content');
        const modalBody = modal.querySelector('.mermaid-modal-body');
        const diagramContainer = modal.querySelector('.mermaid-diagram-container');
        const backdrop = modal.querySelector('.mermaid-modal-backdrop');
        const closeBtn = modal.querySelector('.mermaid-btn-close');
        const zoomInBtn = modal.querySelector('.mermaid-btn-zoom-in');
        const zoomOutBtn = modal.querySelector('.mermaid-btn-zoom-out');
        const resetBtn = modal.querySelector('.mermaid-btn-reset');

        // Prevent clicks on modal content from bubbling to backdrop
        modalContent.addEventListener('click', (e) => {
            console.log('🛡️ Modal content clicked, stopping propagation');
            e.stopPropagation();
        });

        // Clear container first to ensure no duplicates
        diagramContainer.innerHTML = '';

        // Append cloned SVG to container
        diagramContainer.appendChild(clonedSvg);
        const zoomedSvg = clonedSvg;

        // Set cursor for modal body (for drag) since SVG has pointerEvents: none
        modalBody.style.cursor = 'grab';

        console.log(`📊 Container has ${diagramContainer.children.length} child(ren)`);

        // Set explicit dimensions to prevent CSS constraints from shrinking it
        zoomedSvg.style.width = `${originalWidth}px`;
        zoomedSvg.style.height = `${originalHeight}px`;
        zoomedSvg.setAttribute('width', originalWidth);
        zoomedSvg.setAttribute('height', originalHeight);
        console.log(`📏 Set SVG size to ${originalWidth}x${originalHeight}px`);

        // Zoom state
        let scale = 1;
        let posX = 0;
        let posY = 0;
        let isDragging = false;
        let startX = 0;
        let startY = 0;

        // Apply transform
        function updateTransform() {
            // Always include translateZ(0) for GPU acceleration
            diagramContainer.style.transform = `translate(${posX}px, ${posY}px) scale(${scale}) translateZ(0)`;
            console.log(`🔄 Transform updated: translate(${posX.toFixed(0)}px, ${posY.toFixed(0)}px) scale(${scale.toFixed(2)})`);

            // Check if elements are still in DOM
            const containerInDOM = document.body.contains(diagramContainer);
            const svgInDOM = diagramContainer.contains(zoomedSvg);
            const svgCount = diagramContainer.querySelectorAll('svg').length;

            console.log(`🔍 Container in DOM: ${containerInDOM}, SVG in container: ${svgInDOM}, SVG count: ${svgCount}`);
            console.log(`📊 Container size: ${diagramContainer.offsetWidth}x${diagramContainer.offsetHeight}`);
            console.log(`📊 SVG size: ${zoomedSvg.offsetWidth}x${zoomedSvg.offsetHeight}`);
            console.log(`📊 Container display: ${diagramContainer.style.display}, visibility: ${diagramContainer.style.visibility}`);
        }

        // Enable GPU acceleration and prevent rendering issues
        diagramContainer.style.willChange = 'transform';
        diagramContainer.style.backfaceVisibility = 'hidden';

        // Set initial transform
        updateTransform();

        // Zoom functions
        function zoomIn() {
            // Add transition class for smooth zoom animation
            diagramContainer.classList.add('zoom-transition');
            scale = Math.min(scale * 1.2, 5);
            updateTransform();
            console.log('🔍 Zoom in:', scale);
            // Remove transition after animation completes
            setTimeout(() => diagramContainer.classList.remove('zoom-transition'), 200);
        }

        function zoomOut() {
            // Add transition class for smooth zoom animation
            diagramContainer.classList.add('zoom-transition');
            scale = Math.max(scale / 1.2, 0.5);
            updateTransform();
            console.log('🔍 Zoom out:', scale);
            // Remove transition after animation completes
            setTimeout(() => diagramContainer.classList.remove('zoom-transition'), 200);
        }

        function resetZoom() {
            // Add transition class for smooth reset animation
            diagramContainer.classList.add('zoom-transition');
            scale = 1;
            posX = 0;
            posY = 0;
            updateTransform();
            console.log('🔍 Reset zoom');
            // Remove transition after animation completes
            setTimeout(() => diagramContainer.classList.remove('zoom-transition'), 200);
        }

        // Button event listeners
        zoomInBtn.addEventListener('click', zoomIn);
        zoomOutBtn.addEventListener('click', zoomOut);
        resetBtn.addEventListener('click', resetZoom);

        // Close modal
        function closeModal() {
            console.log('❌ Mermaid Zoom: Closing modal');
            // Remove all event listeners before closing
            modalBody.removeEventListener('mousedown', handleMouseDown);
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            document.removeEventListener('keydown', handleKeyboard);

            modal.classList.add('closing');
            setTimeout(() => {
                document.body.removeChild(modal);
            }, 200);
        }

        closeBtn.addEventListener('click', closeModal);

        // Only close when clicking directly on backdrop (not when event bubbles from content)
        backdrop.addEventListener('click', (e) => {
            if (e.target === backdrop) {
                console.log('🎯 Backdrop clicked directly');
                closeModal();
            } else {
                console.log('⛔ Click bubbled to backdrop, ignoring');
            }
        });

        // Keyboard shortcuts
        function handleKeyboard(e) {
            if (e.key === 'Escape') {
                closeModal();
            } else if ((e.ctrlKey || e.metaKey) && e.key === '=') {
                e.preventDefault();
                zoomIn();
            } else if ((e.ctrlKey || e.metaKey) && e.key === '-') {
                e.preventDefault();
                zoomOut();
            } else if ((e.ctrlKey || e.metaKey) && e.key === '0') {
                e.preventDefault();
                resetZoom();
            }
        }

        document.addEventListener('keydown', handleKeyboard);

        // Mouse wheel zoom
        diagramContainer.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                zoomIn();
            } else {
                zoomOut();
            }
        });

        // Drag functionality with proper event cleanup
        function handleMouseDown(e) {
            console.log('🖱️ MouseDown event:', e.target.tagName, e.target.className);

            // Prevent if clicking on buttons or modal header
            if (e.target.closest('.mermaid-btn') || e.target.closest('.mermaid-modal-header')) {
                console.log('⛔ Ignored: button or header click');
                return;
            }

            // Only start drag if clicking on modal body area
            if (!e.target.closest('.mermaid-modal-body')) {
                console.log('⛔ Ignored: not in modal body');
                return;
            }

            console.log('✅ Drag started');
            isDragging = true;
            startX = e.clientX - posX;
            startY = e.clientY - posY;
            modalBody.style.cursor = 'grabbing';
            // Remove transition during drag to prevent ghosting
            diagramContainer.classList.remove('zoom-transition');
            e.preventDefault(); // Prevent text selection while dragging
            e.stopPropagation(); // Stop event from bubbling
        }

        function handleMouseMove(e) {
            if (isDragging) {
                e.preventDefault();
                e.stopPropagation();

                // Calculate new position
                let newPosX = e.clientX - startX;
                let newPosY = e.clientY - startY;

                // Get modal body dimensions for boundary checking
                const modalBodyRect = modalBody.getBoundingClientRect();
                const maxOffset = Math.max(modalBodyRect.width, modalBodyRect.height) * 0.8;

                // Limit drag distance to prevent diagram from going too far
                newPosX = Math.max(-maxOffset, Math.min(maxOffset, newPosX));
                newPosY = Math.max(-maxOffset, Math.min(maxOffset, newPosY));

                posX = newPosX;
                posY = newPosY;
                updateTransform();
            }
        }

        function handleMouseUp(e) {
            if (isDragging) {
                console.log('✅ Drag ended');
                isDragging = false;
                modalBody.style.cursor = 'grab';
                e.preventDefault();
                e.stopPropagation();
            }
        }

        // Attach mousedown to modal body instead of diagram container
        modalBody.addEventListener('mousedown', handleMouseDown);
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);

        // Trigger fade-in animation and auto-fit horizontal diagrams
        requestAnimationFrame(() => {
            modal.classList.add('active');
            console.log('✅ Mermaid Zoom: Modal animation started');

            // Wait for modal to render, then apply auto-fit for horizontal diagrams
            requestAnimationFrame(() => {
                const isHorizontal = originalAspectRatio > 1.5;

                if (isHorizontal) {
                    const modalBodyRect = modal.querySelector('.mermaid-modal-body').getBoundingClientRect();
                    const availableWidth = modalBodyRect.width * 0.85; // 15% padding

                    // Calculate scale to fit modal width
                    const autoScale = availableWidth / originalWidth;

                    // Apply auto-scale (allow zoom in up to 1.2x for better visibility)
                    scale = Math.min(autoScale, 1.2);

                    console.log(`🔍 Horizontal diagram detected (${originalAspectRatio.toFixed(2)})`);
                    console.log(`📏 Modal width: ${modalBodyRect.width.toFixed(0)}px, Available: ${availableWidth.toFixed(0)}px`);
                    console.log(`📊 Auto-scaling from ${originalWidth.toFixed(0)}px to ${scale.toFixed(2)}x`);

                    updateTransform();
                }
            });
        });
    }
})();
