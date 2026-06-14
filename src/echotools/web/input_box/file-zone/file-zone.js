// ========================= 文件区域控制器 =========================
const FileZoneController = (() => {
    const viewport = document.getElementById("fileZoneViewport");
    const container = document.getElementById("fileContainer");
    const scrollbar = document.getElementById("fileScrollbar");
    const thumb = document.getElementById("fileThumb");
    const popover = document.getElementById("previewPopover");
    const clearAllBtn = document.getElementById("clearAllFilesBtn");

    let thumbY = 0, thumbTargetY = 0, thumbHeight = 24;
    let dragState = null;
    let scrollAnimationId = null;

    let currentPreviewCard = null;
    let previewSuspended = false;
    let clearBtnVisible = false;

    function updateClearButtonVisibility() {
        const shouldShow = AppState.files.length > 3;
        if (shouldShow && !clearBtnVisible) {
            clearBtnVisible = true;
            clearAllBtn.style.pointerEvents = "auto";
            MotionKit.opacityTo(clearAllBtn, 1, 3);
            MotionKit.sizeTo(clearAllBtn, 100, 3);
        } else if (!shouldShow && clearBtnVisible) {
            clearBtnVisible = false;
            clearAllBtn.style.pointerEvents = "none";
            MotionKit.opacityTo(clearAllBtn, 0, 3);
            MotionKit.sizeTo(clearAllBtn, 80, 3);
        }
    }

    function suspendPreviewUntilNextPointerMove() {
        previewSuspended = true;
        window.addEventListener("pointermove", () => { previewSuspended = false; }, { passive: true, once: true });
    }
    function hidePreview(suspend = false) {
        popover.style.display = "none";
        currentPreviewCard = null;
        if (suspend) suspendPreviewUntilNextPointerMove();
    }
    function showPreview(e, content, card) {
        if (previewSuspended) return;
        if (!card || !card.isConnected) return;
        currentPreviewCard = card;
        popover.style.display = "block";
        popover.textContent = content.substring(0, 120) + (content.length > 120 ? "..." : "");
        movePreview(e);
    }
    function movePreview(e) {
        popover.style.left = `${e.clientX + 14}px`;
        popover.style.top = `${e.clientY + 14}px`;
    }

    window.addEventListener("pointermove", (e) => {
        if (popover.style.display !== "block") return;
        if (!currentPreviewCard || !currentPreviewCard.isConnected) { hidePreview(); return; }
        const hit = document.elementFromPoint(e.clientX, e.clientY);
        const card = hit ? hit.closest(".file-card") : null;
        if (!card || !container.contains(card)) hidePreview();
    }, { passive: true });

    function createFileCard(file) {
        const card = document.createElement("div");
        card.className = "file-card relative flex items-center justify-between p-2.5 bg-white border border-[#e5eaf0] rounded-xl shadow-xs";
        card.setAttribute("data-file-id", file.id);

        const info = document.createElement("div");
        info.className = "flex flex-col min-w-0 flex-1 pr-3";
        const nameInput = document.createElement("input");
        nameInput.type = "text";
        nameInput.className = "text-sm font-medium text-[#1e2a3e] bg-transparent border-0 p-0 m-0 w-full truncate focus:text-[#5865bc]";
        nameInput.value = file.name;
        nameInput.addEventListener("change", e => updateFileName(file.id, e.target.value));
        nameInput.addEventListener("blur", e => updateFileName(file.id, e.target.value));
        nameInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); nameInput.blur(); } });
        const sizeSpan = document.createElement("span");
        sizeSpan.className = "text-xs text-[#a8b3cf] mt-0.5 select-none";
        sizeSpan.textContent = `${(file.content.length / 1024).toFixed(2)} KB`;
        info.appendChild(nameInput);
        info.appendChild(sizeSpan);

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-slate-50 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors";
        deleteBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`;
        deleteBtn.addEventListener("click", e => { e.stopPropagation(); removeFile(file.id); });

        card.appendChild(info);
        card.appendChild(deleteBtn);

        card.addEventListener("mouseenter", (e) => {
            if (document.activeElement !== nameInput) showPreview(e, file.content, card);
        });
        card.addEventListener("mousemove", (e) => { if (currentPreviewCard === card) movePreview(e); });
        card.addEventListener("mouseleave", () => { if (currentPreviewCard === card) hidePreview(); });
        nameInput.addEventListener("focus", () => hidePreview());

        return card;
    }

    function addFileCard(file) {
        const card = createFileCard(file);
        container.appendChild(card);
        card.style.opacity = "0";
        card.style.transform = "scale(0.92)";
        card.style.transition = "opacity 0.3s cubic-bezier(0.2,0.9,0.4,1.1), transform 0.3s cubic-bezier(0.2,0.9,0.4,1.1), border-color 0.15s ease";
        requestAnimationFrame(() => { card.style.opacity = "1"; card.style.transform = "scale(1)"; });

        updateContainerHeight();
        updateScrollbar(false);
        animateScrollToBottom();
        updateClearButtonVisibility();
    }

    function removeFileCard(fileId) {
        const card = document.querySelector(`.file-card[data-file-id="${fileId}"]`);
        if (card) {
            if (currentPreviewCard === card) hidePreview(true);
            card.style.transition = "opacity 0.18s ease, transform 0.18s ease";
            card.style.opacity = "0";
            card.style.transform = "scale(0.88)";
            setTimeout(() => {
                if (card.parentNode) card.remove();
                updateContainerHeight();
                updateScrollbar(true);
                updateClearButtonVisibility();
            }, 180);
        }
    }

    function clearAllFileCards() {
        const cards = Array.from(document.querySelectorAll('.file-card'));
        hidePreview(true);
        if (cards.length === 0) {
            updateContainerHeight();
            updateScrollbar(true);
            updateClearButtonVisibility();
            return;
        }
        cards.forEach((card, index) => {
            card.style.transition = "opacity 0.18s ease, transform 0.18s ease";
            card.style.opacity = "0";
            card.style.transform = "scale(0.88)";
            setTimeout(() => {
                if (card.parentNode) card.remove();
                if (index === cards.length - 1) {
                    updateContainerHeight();
                    updateScrollbar(true);
                    updateClearButtonVisibility();
                }
            }, 180);
        });
    }

    function updateContainerHeight() {
        const count = AppState.files.length;
        if (count === 0) viewport.style.height = "0px";
        else if (count === 1) viewport.style.height = "58px";
        else viewport.style.height = "120px";
    }

    function animateScrollToBottom() {
        if (scrollAnimationId) cancelAnimationFrame(scrollAnimationId);
        const startScroll = container.scrollTop;
        const targetScroll = container.scrollHeight - container.clientHeight;
        if (targetScroll <= 0) return;
        const startTime = performance.now();
        const duration = 320;
        function step(now) {
            const elapsed = now - startTime;
            let t = Math.min(1, elapsed / duration);
            const easeOut = 1 - Math.pow(1 - t, 3);
            container.scrollTop = startScroll + (targetScroll - startScroll) * easeOut;
            updateScrollbar(false);
            if (t < 1) scrollAnimationId = requestAnimationFrame(step);
            else { container.scrollTop = targetScroll; updateScrollbar(true); scrollAnimationId = null; }
        }
        scrollAnimationId = requestAnimationFrame(step);
    }

    function updateFileName(id, newName) {
        const file = AppState.files.find(f => f.id === id);
        if (!file) return;
        let cleanedName = newName.trim();
        if (!cleanedName) cleanedName = `Pasted_Text_${Date.now()}`;
        if (!cleanedName.toLowerCase().endsWith(".txt")) cleanedName += ".txt";
        file.name = cleanedName;
        const card = document.querySelector(`.file-card[data-file-id="${id}"]`);
        if (card) {
            const input = card.querySelector('input');
            if (input && input.value !== cleanedName) input.value = cleanedName;
        }
    }

    function addFile(content) {
        const id = crypto.randomUUID();
        const name = `Pasted_Text_${Date.now()}.txt`;
        const file = { id, name, content };
        AppState.files.push(file);
        addFileCard(file);
    }

    function removeFile(id) {
        const index = AppState.files.findIndex(f => f.id === id);
        if (index !== -1) {
            AppState.files.splice(index, 1);
            removeFileCard(id);
        }
        hidePreview(true);
    }

    function clearAllFiles() {
        if (AppState.files.length === 0) return;
        AppState.files = [];
        hidePreview(true);
        clearAllFileCards();
    }

    function updateScrollbar(immediate = false) {
        const maxScroll = Math.max(0, container.scrollHeight - container.clientHeight);
        const trackHeight = Math.max(0, viewport.clientHeight - 8);
        if (maxScroll <= 1 || trackHeight <= 0) {
            scrollbar.classList.remove("is-scrollable");
            thumbTargetY = 0; thumbY = 0;
            thumb.style.transform = "translate3d(0,0,0)";
            return;
        }
        scrollbar.classList.add("is-scrollable");
        thumbHeight = MotionKit.clamp((container.clientHeight / container.scrollHeight) * trackHeight, 24, trackHeight);
        const maxThumbY = Math.max(0, trackHeight - thumbHeight);
        thumbTargetY = (container.scrollTop / maxScroll) * maxThumbY;
        thumb.style.height = `${thumbHeight}px`;
        if (immediate) { thumbY = thumbTargetY; thumb.style.transform = `translate3d(0,${thumbY}px,0)`; }
    }

    MotionKit.createLoop(() => {
        const diff = thumbTargetY - thumbY;
        if (Math.abs(diff) < 0.2) thumbY = thumbTargetY;
        else thumbY += diff * 0.25;
        thumb.style.transform = `translate3d(0,${thumbY}px,0)`;
    });
    container.addEventListener("scroll", () => updateScrollbar(false), { passive: true });

    thumb.addEventListener("pointerdown", e => {
        e.preventDefault();
        const maxScroll = Math.max(0, container.scrollHeight - container.clientHeight);
        const trackHeight = Math.max(0, viewport.clientHeight - 8);
        const curThumbHeight = parseFloat(thumb.style.height) || 24;
        const maxThumbY = Math.max(0, trackHeight - curThumbHeight);
        dragState = { pointerId: e.pointerId, startY: e.clientY, startScrollTop: container.scrollTop, maxScroll, maxThumbY };
        thumb.setPointerCapture(e.pointerId);
    });
    thumb.addEventListener("pointermove", e => {
        if (!dragState || dragState.pointerId !== e.pointerId) return;
        e.preventDefault();
        const deltaY = e.clientY - dragState.startY;
        const ratio = dragState.maxThumbY > 0 ? deltaY / dragState.maxThumbY : 0;
        container.scrollTop = MotionKit.clamp(dragState.startScrollTop + ratio * dragState.maxScroll, 0, dragState.maxScroll);
        updateScrollbar(true);
    });
    const releaseDrag = e => { if (dragState && dragState.pointerId === e.pointerId) { thumb.releasePointerCapture(e.pointerId); dragState = null; } };
    thumb.addEventListener("pointerup", releaseDrag);
    thumb.addEventListener("pointercancel", releaseDrag);

    clearAllBtn.addEventListener("click", clearAllFiles);

    return { addFile, clearAllFiles };
})();
