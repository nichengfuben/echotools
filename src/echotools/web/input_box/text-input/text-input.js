// ========================= 文本框核心 =========================
(() => {
    const textarea = document.getElementById("chatInput");
    const viewport = document.getElementById("textViewport");
    const scrollbar = document.getElementById("customScrollbar");
    const thumb = document.getElementById("customThumb");
    const caret = document.getElementById("customCaret");
    const sendButton = document.getElementById("sendButton");

    const minRows = 4, maxRows = 6;
    const metrics = { lineHeight: 24, minHeight: 96, maxHeight: 144 };
    let visualHeight = 96, targetHeight = 96, heightFrame = 0;
    let thumbY = 0, thumbTargetY = 0, thumbHeight = 28, thumbFrame = 0;
    let caretX = 0, caretY = 0, caretTargetX = 0, caretTargetY = 0, caretHeight = 24, caretFrame = 0, caretReady = false;
    let dragState = null;

    const mirror = document.createElement("div");
    mirror.setAttribute("aria-hidden", "true");
    mirror.style.cssText = "position:fixed;left:0;top:0;visibility:hidden;pointer-events:none;z-index:-1;white-space:pre-wrap;overflow-wrap:break-word;word-break:break-word;";
    document.body.appendChild(mirror);

    function refreshMetrics() {
        const c = getComputedStyle(textarea);
        const lh = Number.parseFloat(c.lineHeight), fs = Number.parseFloat(c.fontSize);
        metrics.lineHeight = Number.isFinite(lh) ? lh : fs * 1.5;
        metrics.minHeight = metrics.lineHeight * minRows;
        metrics.maxHeight = metrics.lineHeight * maxRows;
    }
    function applyHeight(h) { visualHeight = h; viewport.style.height = `${h}px`; textarea.style.height = `${h}px`; updateScrollbar(false); updateCaretTarget(false); }
    function measureContentHeight() {
        const prev = textarea.style.height, prevST = textarea.scrollTop;
        textarea.style.height = "0px";
        const h = textarea.scrollHeight;
        textarea.style.height = prev; textarea.scrollTop = prevST;
        return h;
    }
    function requestHeightUpdate(immediate = false) {
        refreshMetrics();
        targetHeight = MotionKit.clamp(measureContentHeight(), metrics.minHeight, metrics.maxHeight);
        if (immediate) { applyHeight(targetHeight); return; }
        if (!heightFrame) heightFrame = requestAnimationFrame(animateHeight);
    }
    function animateHeight() {
        heightFrame = 0;
        const diff = targetHeight - visualHeight;
        if (Math.abs(diff) < 0.35) { applyHeight(targetHeight); return; }
        applyHeight(visualHeight + diff * 0.18);
        heightFrame = requestAnimationFrame(animateHeight);
    }
    function updateScrollbar(immediate = false) {
        const maxScroll = Math.max(0, textarea.scrollHeight - textarea.clientHeight);
        const trackHeight = Math.max(0, viewport.clientHeight - 8);
        if (maxScroll <= 1 || trackHeight <= 0) {
            scrollbar.classList.remove("is-scrollable");
            thumbTargetY = 0; thumbY = 0;
            thumb.style.height = "28px";
            thumb.style.transform = "translate3d(0,0,0)";
            return;
        }
        scrollbar.classList.add("is-scrollable");
        thumbHeight = MotionKit.clamp((textarea.clientHeight / textarea.scrollHeight) * trackHeight, 28, trackHeight);
        const maxThumbY = Math.max(0, trackHeight - thumbHeight);
        thumbTargetY = maxScroll > 0 ? (textarea.scrollTop / maxScroll) * maxThumbY : 0;
        thumb.style.height = `${thumbHeight}px`;
        if (immediate) { thumbY = thumbTargetY; renderThumb(); return; }
        if (!thumbFrame) thumbFrame = requestAnimationFrame(animateThumb);
    }
    function renderThumb() { thumb.style.transform = `translate3d(0,${thumbY}px,0)`; }
    function animateThumb() {
        thumbFrame = 0;
        const diff = thumbTargetY - thumbY;
        if (Math.abs(diff) < 0.25) { thumbY = thumbTargetY; renderThumb(); return; }
        thumbY += diff * 0.28;
        renderThumb();
        thumbFrame = requestAnimationFrame(animateThumb);
    }
    function syncMirrorStyle() {
        const c = getComputedStyle(textarea);
        ["boxSizing","fontFamily","fontSize","fontWeight","fontStyle","letterSpacing","textTransform","wordSpacing","textIndent","lineHeight","paddingTop","paddingRight","paddingBottom","paddingLeft"].forEach(p => mirror.style[p] = c[p]);
        mirror.style.width = `${textarea.clientWidth}px`;
    }
    function getCaretCoordinates() {
        syncMirrorStyle();
        const pos = textarea.selectionEnd;
        mirror.textContent = textarea.value.slice(0, pos);
        const marker = document.createElement("span");
        marker.textContent = "\u200b";
        marker.style.cssText = `display:inline-block;width:1px;height:${metrics.lineHeight}px;`;
        mirror.appendChild(marker);
        const mr = marker.getBoundingClientRect(), mir = mirror.getBoundingClientRect();
        return { x: mr.left - mir.left - textarea.scrollLeft, y: mr.top - mir.top - textarea.scrollTop, height: metrics.lineHeight };
    }
    function updateCaretTarget(immediate = false) {
        const focused = document.activeElement === textarea;
        const collapsed = textarea.selectionStart === textarea.selectionEnd;
        if (!focused || !collapsed) { caret.classList.remove("is-visible","is-moving"); return; }
        const coords = getCaretCoordinates();
        caretTargetX = MotionKit.clamp(coords.x, 0, Math.max(0, textarea.clientWidth - 3));
        caretTargetY = coords.y;
        caretHeight = coords.height;
        if (caretTargetY < -metrics.lineHeight || caretTargetY > textarea.clientHeight) { caret.classList.remove("is-visible","is-moving"); return; }
        caret.classList.add("is-visible");
        caret.style.height = `${caretHeight}px`;
        if (immediate || !caretReady) { caretX = caretTargetX; caretY = caretTargetY; caretReady = true; renderCaret(); return; }
        if (!caretFrame) caretFrame = requestAnimationFrame(animateCaret);
    }
    function renderCaret() { caret.style.transform = `translate3d(${caretX}px,${caretY}px,0)`; }
    function animateCaret() {
        caretFrame = 0;
        const dx = caretTargetX - caretX, dy = caretTargetY - caretY;
        if (Math.abs(dx) < 0.25 && Math.abs(dy) < 0.25) { caretX = caretTargetX; caretY = caretTargetY; renderCaret(); caret.classList.remove("is-moving"); return; }
        caret.classList.add("is-moving");
        caretX += dx * 0.38; caretY += dy * 0.38;
        renderCaret();
        caretFrame = requestAnimationFrame(animateCaret);
    }
    function checkLengthLimit() {
        const len = textarea.value.length;
        if (len > AppState.limitThreshold) { if (!AppState.isTextOverLimit) { AppState.isTextOverLimit = true; ButtonAnimator.switchToLong(); } }
        else { if (AppState.isTextOverLimit) { AppState.isTextOverLimit = false; ButtonAnimator.switchToShort(); } }
    }
    function syncAll(immediate = false) { requestHeightUpdate(immediate); updateScrollbar(immediate); updateCaretTarget(immediate); checkLengthLimit(); }

    textarea.addEventListener("paste", e => {
        e.preventDefault();
        const pasted = (e.clipboardData || window.clipboardData).getData("text");
        if (pasted.length > AppState.limitThreshold) FileZoneController.addFile(pasted);
        else {
            const start = textarea.selectionStart, end = textarea.selectionEnd;
            textarea.value = textarea.value.slice(0, start) + pasted + textarea.value.slice(end);
            textarea.selectionStart = textarea.selectionEnd = start + pasted.length;
            syncAll(false);
        }
    });
    textarea.addEventListener("input", () => syncAll(false));
    textarea.addEventListener("scroll", () => { updateScrollbar(false); updateCaretTarget(false); }, { passive: true });
    textarea.addEventListener("focus", () => updateCaretTarget(true));
    textarea.addEventListener("blur", () => caret.classList.remove("is-visible","is-moving"));
    textarea.addEventListener("click", () => requestAnimationFrame(() => updateCaretTarget(true)));
    textarea.addEventListener("keyup", () => syncAll(false));

    sendButton.addEventListener("click", () => {
        if (AppState.isTextOverLimit) {
            FileZoneController.addFile(textarea.value);
            textarea.value = "";
            AppState.isTextOverLimit = false;
            ButtonAnimator.switchToShort();
            syncAll(false);
            textarea.focus();
            return;
        }
        if (!textarea.value.trim() && AppState.files.length === 0) { textarea.focus(); updateCaretTarget(true); return; }
        textarea.value = ""; textarea.scrollTop = 0;
        if (AppState.files.length > 0) FileZoneController.clearAllFiles();
        textarea.focus();
        syncAll(false);
    });

    window.addEventListener("resize", () => syncAll(true));
    refreshMetrics();
    applyHeight(metrics.minHeight);
    syncAll(true);

    thumb.addEventListener("pointerdown", e => {
        if (!scrollbar.classList.contains("is-scrollable")) return;
        e.preventDefault();
        const maxScroll = Math.max(0, textarea.scrollHeight - textarea.clientHeight);
        const trackHeight = Math.max(0, viewport.clientHeight - 8);
        const currentThumbHeight = parseFloat(thumb.style.height) || 28;
        const maxThumbY = Math.max(0, trackHeight - currentThumbHeight);
        dragState = { pointerId: e.pointerId, startY: e.clientY, startScrollTop: textarea.scrollTop, maxScroll, maxThumbY };
        thumb.setPointerCapture(e.pointerId);
        thumb.style.cursor = "grabbing";
    });
    thumb.addEventListener("pointermove", e => {
        if (!dragState || dragState.pointerId !== e.pointerId) return;
        e.preventDefault();
        const deltaY = e.clientY - dragState.startY;
        const ratio = dragState.maxThumbY > 0 ? deltaY / dragState.maxThumbY : 0;
        textarea.scrollTop = MotionKit.clamp(dragState.startScrollTop + ratio * dragState.maxScroll, 0, dragState.maxScroll);
        updateScrollbar(true);
    });
    const releaseDragText = e => { if (dragState && dragState.pointerId === e.pointerId) { thumb.releasePointerCapture(e.pointerId); dragState = null; thumb.style.cursor = ""; } };
    thumb.addEventListener("pointerup", releaseDragText);
    thumb.addEventListener("pointercancel", releaseDragText);
})();
