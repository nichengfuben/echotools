// ========================= 文件区域控制器 =========================
const fzViewport = document.getElementById("fileZoneViewport");
const fzContainer = document.getElementById("fileContainer");
const fzScrollbar = document.getElementById("fileScrollbar");
const fzThumb = document.getElementById("fileThumb");
const fzPopover = document.getElementById("previewPopover");
const fzClearAllBtn = document.getElementById("clearAllFilesBtn");

let fzThumbY = 0, fzThumbTargetY = 0, fzThumbHeight = 24;
let fzDragState = null;
let fzScrollAnimationId = null;
let fzCurrentPreviewCard = null;
let fzPreviewSuspended = false;
let fzClearBtnVisible = false;

function fzUpdateClearButtonVisibility() {
    const shouldShow = AppState.files.length > 3;
    if (shouldShow && !fzClearBtnVisible) {
        fzClearBtnVisible = true;
        fzClearAllBtn.style.pointerEvents = "auto";
        MotionKit.opacityTo(fzClearAllBtn, 1, 3);
        MotionKit.sizeTo(fzClearAllBtn, 100, 3);
    } else if (!shouldShow && fzClearBtnVisible) {
        fzClearBtnVisible = false;
        fzClearAllBtn.style.pointerEvents = "none";
        MotionKit.opacityTo(fzClearAllBtn, 0, 3);
        MotionKit.sizeTo(fzClearAllBtn, 80, 3);
    }
}

function fzSuspendPreviewUntilNextPointerMove() {
    fzPreviewSuspended = true;
    window.addEventListener("pointermove", () => { fzPreviewSuspended = false; }, { passive: true, once: true });
}

function fzHidePreview(suspend) {
    fzPopover.style.display = "none";
    fzCurrentPreviewCard = null;
    if (suspend) fzSuspendPreviewUntilNextPointerMove();
}

function fzShowPreview(e, content, card) {
    if (fzPreviewSuspended) return;
    if (!card || !card.isConnected) return;
    fzCurrentPreviewCard = card;
    fzPopover.style.display = "block";
    fzPopover.textContent = content.substring(0, 120) + (content.length > 120 ? "..." : "");
    fzMovePreview(e);
}

function fzMovePreview(e) {
    fzPopover.style.left = `${e.clientX + 14}px`;
    fzPopover.style.top = `${e.clientY + 14}px`;
}

function fzBindPreviewPointer() {
    window.addEventListener("pointermove", (e) => {
        if (fzPopover.style.display !== "block") return;
        if (!fzCurrentPreviewCard || !fzCurrentPreviewCard.isConnected) { fzHidePreview(); return; }
        const hit = document.elementFromPoint(e.clientX, e.clientY);
        const card = hit ? hit.closest(".file-card") : null;
        if (!card || !fzContainer.contains(card)) fzHidePreview();
    }, { passive: true });
}

function fzCreateFileCard(file) {
    const card = document.createElement("div");
    card.className = "file-card relative flex items-center justify-between p-2.5 bg-white border border-[#e5eaf0] rounded-xl shadow-xs";
    card.setAttribute("data-file-id", file.id);
    const info = document.createElement("div");
    info.className = "flex flex-col min-w-0 flex-1 pr-3";
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "text-sm font-medium text-[#1e2a3e] bg-transparent border-0 p-0 m-0 w-full truncate focus:text-[#5865bc]";
    nameInput.value = file.name;
    nameInput.addEventListener("change", e => fzUpdateFileName(file.id, e.target.value));
    nameInput.addEventListener("blur", e => fzUpdateFileName(file.id, e.target.value));
    nameInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); nameInput.blur(); } });
    const sizeSpan = document.createElement("span");
    sizeSpan.className = "text-xs text-[#a8b3cf] mt-0.5 select-none";
    sizeSpan.textContent = `${(file.content.length / 1024).toFixed(2)} KB`;
    info.appendChild(nameInput);
    info.appendChild(sizeSpan);
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-slate-50 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors";
    deleteBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`;
    deleteBtn.addEventListener("click", e => { e.stopPropagation(); fzRemoveFile(file.id); });
    card.appendChild(info);
    card.appendChild(deleteBtn);
    card.addEventListener("mouseenter", (e) => {
        if (document.activeElement !== nameInput) fzShowPreview(e, file.content, card);
    });
    card.addEventListener("mousemove", (e) => { if (fzCurrentPreviewCard === card) fzMovePreview(e); });
    card.addEventListener("mouseleave", () => { if (fzCurrentPreviewCard === card) fzHidePreview(); });
    nameInput.addEventListener("focus", () => fzHidePreview());
    return card;
}

function fzAddFileCard(file) {
    const card = fzCreateFileCard(file);
    fzContainer.appendChild(card);
    card.style.opacity = "0";
    card.style.transform = "scale(0.92)";
    card.style.transition = "opacity 0.3s cubic-bezier(0.2,0.9,0.4,1.1), transform 0.3s cubic-bezier(0.2,0.9,0.4,1.1), border-color 0.15s ease";
    requestAnimationFrame(() => { card.style.opacity = "1"; card.style.transform = "scale(1)"; });
    fzUpdateContainerHeight();
    fzUpdateScrollbar(false);
    fzAnimateScrollToBottom();
    fzUpdateClearButtonVisibility();
}

function fzRemoveFileCard(fileId) {
    const card = document.querySelector(`.file-card[data-file-id="${fileId}"]`);
    if (!card) return;
    if (fzCurrentPreviewCard === card) fzHidePreview(true);
    card.style.transition = "opacity 0.18s ease, transform 0.18s ease";
    card.style.opacity = "0";
    card.style.transform = "scale(0.88)";
    setTimeout(() => {
        if (card.parentNode) card.remove();
        fzUpdateContainerHeight();
        fzUpdateScrollbar(true);
        fzUpdateClearButtonVisibility();
    }, 180);
}

function fzAnimateCardOut(card, onDone) {
    card.style.transition = "opacity 0.18s ease, transform 0.18s ease";
    card.style.opacity = "0";
    card.style.transform = "scale(0.88)";
    setTimeout(() => {
        if (card.parentNode) card.remove();
        if (onDone) onDone();
    }, 180);
}

function fzClearAllFileCards() {
    const cards = Array.from(document.querySelectorAll('.file-card'));
    fzHidePreview(true);
    if (cards.length === 0) {
        fzUpdateContainerHeight();
        fzUpdateScrollbar(true);
        fzUpdateClearButtonVisibility();
        return;
    }
    cards.forEach((card, index) => {
        fzAnimateCardOut(card, index === cards.length - 1 ? () => {
            fzUpdateContainerHeight();
            fzUpdateScrollbar(true);
            fzUpdateClearButtonVisibility();
        } : null);
    });
}

function fzUpdateContainerHeight() {
    const count = AppState.files.length;
    if (count === 0) fzViewport.style.height = "0px";
    else if (count === 1) fzViewport.style.height = "58px";
    else fzViewport.style.height = "120px";
}

function fzAnimateScrollToBottom() {
    if (fzScrollAnimationId) cancelAnimationFrame(fzScrollAnimationId);
    const startScroll = fzContainer.scrollTop;
    const targetScroll = fzContainer.scrollHeight - fzContainer.clientHeight;
    if (targetScroll <= 0) return;
    const startTime = performance.now();
    const duration = 320;
    function step(now) {
        const elapsed = now - startTime;
        const t = Math.min(1, elapsed / duration);
        const easeOut = 1 - Math.pow(1 - t, 3);
        fzContainer.scrollTop = startScroll + (targetScroll - startScroll) * easeOut;
        fzUpdateScrollbar(false);
        if (t < 1) fzScrollAnimationId = requestAnimationFrame(step);
        else { fzContainer.scrollTop = targetScroll; fzUpdateScrollbar(true); fzScrollAnimationId = null; }
    }
    fzScrollAnimationId = requestAnimationFrame(step);
}

function fzUpdateFileName(id, newName) {
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

function fzAddFile(content) {
    const id = crypto.randomUUID();
    const file = { id, name: `Pasted_Text_${Date.now()}.txt`, content };
    AppState.files.push(file);
    fzAddFileCard(file);
}

function fzRemoveFile(id) {
    const index = AppState.files.findIndex(f => f.id === id);
    if (index !== -1) {
        AppState.files.splice(index, 1);
        fzRemoveFileCard(id);
    }
    fzHidePreview(true);
}

function fzClearAllFiles() {
    if (AppState.files.length === 0) return;
    AppState.files = [];
    fzHidePreview(true);
    fzClearAllFileCards();
}

function fzUpdateScrollbar(immediate) {
    const maxScroll = Math.max(0, fzContainer.scrollHeight - fzContainer.clientHeight);
    const trackHeight = Math.max(0, fzViewport.clientHeight - 8);
    if (maxScroll <= 1 || trackHeight <= 0) {
        fzScrollbar.classList.remove("is-scrollable");
        fzThumbTargetY = 0; fzThumbY = 0;
        fzThumb.style.transform = "translate3d(0,0,0)";
        return;
    }
    fzScrollbar.classList.add("is-scrollable");
    fzThumbHeight = MotionKit.clamp((fzContainer.clientHeight / fzContainer.scrollHeight) * trackHeight, 24, trackHeight);
    const maxThumbY = Math.max(0, trackHeight - fzThumbHeight);
    fzThumbTargetY = (fzContainer.scrollTop / maxScroll) * maxThumbY;
    fzThumb.style.height = `${fzThumbHeight}px`;
    if (immediate) { fzThumbY = fzThumbTargetY; fzThumb.style.transform = `translate3d(0,${fzThumbY}px,0)`; }
}

function fzBindScrollbarDrag() {
    MotionKit.createLoop(() => {
        const diff = fzThumbTargetY - fzThumbY;
        if (Math.abs(diff) < 0.2) fzThumbY = fzThumbTargetY;
        else fzThumbY += diff * 0.25;
        fzThumb.style.transform = `translate3d(0,${fzThumbY}px,0)`;
    });
    fzContainer.addEventListener("scroll", () => fzUpdateScrollbar(false), { passive: true });
    fzThumb.addEventListener("pointerdown", e => {
        e.preventDefault();
        const maxScroll = Math.max(0, fzContainer.scrollHeight - fzContainer.clientHeight);
        const trackHeight = Math.max(0, fzViewport.clientHeight - 8);
        const curThumbHeight = parseFloat(fzThumb.style.height) || 24;
        const maxThumbY = Math.max(0, trackHeight - curThumbHeight);
        fzDragState = { pointerId: e.pointerId, startY: e.clientY, startScrollTop: fzContainer.scrollTop, maxScroll, maxThumbY };
        fzThumb.setPointerCapture(e.pointerId);
    });
    fzThumb.addEventListener("pointermove", e => {
        if (!fzDragState || fzDragState.pointerId !== e.pointerId) return;
        e.preventDefault();
        const deltaY = e.clientY - fzDragState.startY;
        const ratio = fzDragState.maxThumbY > 0 ? deltaY / fzDragState.maxThumbY : 0;
        fzContainer.scrollTop = MotionKit.clamp(fzDragState.startScrollTop + ratio * fzDragState.maxScroll, 0, fzDragState.maxScroll);
        fzUpdateScrollbar(true);
    });
    const releaseDrag = e => {
        if (fzDragState && fzDragState.pointerId === e.pointerId) {
            fzThumb.releasePointerCapture(e.pointerId);
            fzDragState = null;
        }
    };
    fzThumb.addEventListener("pointerup", releaseDrag);
    fzThumb.addEventListener("pointercancel", releaseDrag);
}

function fzInit() {
    fzBindPreviewPointer();
    fzBindScrollbarDrag();
    fzClearAllBtn.addEventListener("click", fzClearAllFiles);
}

const FileZoneController = { addFile: fzAddFile, clearAllFiles: fzClearAllFiles, init: fzInit };
fzInit();
