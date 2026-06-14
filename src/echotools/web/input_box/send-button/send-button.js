const ButtonAnimator = (() => {
    const sendBtn = document.getElementById("sendButton");
    const btnTextSpan = document.getElementById("btnText");
    const SHORT_TEXT = "发送";
    const LONG_TEXT = "输入框内容转为文件";
    let currentFullText = SHORT_TEXT;
    let animationFrameId = null;

    const measureSpan = document.createElement("span");
    measureSpan.style.cssText = `position:fixed;left:-9999px;top:-9999px;visibility:hidden;white-space:nowrap;font-size:0.875rem;font-weight:500;font-family:inherit;padding:0 16px;line-height:44px;`;
    document.body.appendChild(measureSpan);

    function getTextWidth(text) { measureSpan.textContent = text; return measureSpan.offsetWidth - 32; }
    const FIXED_WIDTH = 26;

    function getMaxFitChars(fullText, availableWidth) {
        if (availableWidth <= 0) return 0;
        let left = 0, right = fullText.length;
        while (left < right) {
            const mid = Math.ceil((left + right) / 2);
            if (getTextWidth(fullText.substring(0, mid)) <= availableWidth) left = mid;
            else right = mid - 1;
        }
        return left;
    }

    function updateDisplayText() {
        if (!sendBtn) return;
        const availableForText = Math.max(0, sendBtn.offsetWidth - FIXED_WIDTH - 32);
        let maxChars = getMaxFitChars(currentFullText, availableForText);
        if (maxChars === 0 && currentFullText.length > 0 && availableForText > 10) maxChars = 1;
        btnTextSpan.textContent = currentFullText.substring(0, maxChars);
    }

    function startWidthWatcher() {
        if (animationFrameId) cancelAnimationFrame(animationFrameId);
        let lastWidth = sendBtn.offsetWidth;
        function watch() {
            const w = sendBtn.offsetWidth;
            if (Math.abs(w - lastWidth) > 1) { lastWidth = w; updateDisplayText(); }
            animationFrameId = requestAnimationFrame(watch);
        }
        animationFrameId = requestAnimationFrame(watch);
    }

    function setFullText(newFullText) {
        if (currentFullText === newFullText) return;
        currentFullText = newFullText;
        updateDisplayText();
        const targetBtnWidth = getTextWidth(currentFullText) + FIXED_WIDTH + 32;
        MotionKit.widthTo(sendBtn, targetBtnWidth, 6);
    }
    function switchToLong() { setFullText(LONG_TEXT); }
    function switchToShort() { setFullText(SHORT_TEXT); }

    function init() {
        const initBtnWidth = getTextWidth(SHORT_TEXT) + FIXED_WIDTH + 32;
        MotionKit.setState(sendBtn, { hasExplicitWidth: true, width: initBtnWidth });
        btnTextSpan.textContent = SHORT_TEXT;
        currentFullText = SHORT_TEXT;
        startWidthWatcher();
    }
    return { init, switchToLong, switchToShort };
})();
