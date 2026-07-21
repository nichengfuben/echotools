const sbSendBtn = document.getElementById("sendButton");
const sbTextSpan = document.getElementById("btnText");
const sbShortText = "发送";
const sbLongText = "输入框内容转为文件";
let sbCurrentFullText = sbShortText;
let sbAnimationFrameId = null;

const sbMeasureSpan = document.createElement("span");
sbMeasureSpan.style.cssText = `position:fixed;left:-9999px;top:-9999px;visibility:hidden;white-space:nowrap;font-size:0.875rem;font-weight:500;font-family:inherit;padding:0 16px;line-height:44px;`;
document.body.appendChild(sbMeasureSpan);

function sbGetTextWidth(text) { sbMeasureSpan.textContent = text; return sbMeasureSpan.offsetWidth - 32; }
const sbFixedWidth = 26;

function sbGetMaxFitChars(fullText, availableWidth) {
    if (availableWidth <= 0) return 0;
    let left = 0, right = fullText.length;
    while (left < right) {
        const mid = Math.ceil((left + right) / 2);
        if (sbGetTextWidth(fullText.substring(0, mid)) <= availableWidth) left = mid;
        else right = mid - 1;
    }
    return left;
}

function sbUpdateDisplayText() {
    if (!sbSendBtn) return;
    const availableForText = Math.max(0, sbSendBtn.offsetWidth - sbFixedWidth - 32);
    let maxChars = sbGetMaxFitChars(sbCurrentFullText, availableForText);
    if (maxChars === 0 && sbCurrentFullText.length > 0 && availableForText > 10) maxChars = 1;
    sbTextSpan.textContent = sbCurrentFullText.substring(0, maxChars);
}

function sbStartWidthWatcher() {
    if (sbAnimationFrameId) cancelAnimationFrame(sbAnimationFrameId);
    let lastWidth = sbSendBtn.offsetWidth;
    function watch() {
        const w = sbSendBtn.offsetWidth;
        if (Math.abs(w - lastWidth) > 1) { lastWidth = w; sbUpdateDisplayText(); }
        sbAnimationFrameId = requestAnimationFrame(watch);
    }
    sbAnimationFrameId = requestAnimationFrame(watch);
}

function sbSetFullText(newFullText) {
    if (sbCurrentFullText === newFullText) return;
    sbCurrentFullText = newFullText;
    sbUpdateDisplayText();
    const targetBtnWidth = sbGetTextWidth(sbCurrentFullText) + sbFixedWidth + 32;
    MotionKit.widthTo(sbSendBtn, targetBtnWidth, 6);
}

function sbSwitchToLong() { sbSetFullText(sbLongText); }
function sbSwitchToShort() { sbSetFullText(sbShortText); }

function sbInit() {
    const initBtnWidth = sbGetTextWidth(sbShortText) + sbFixedWidth + 32;
    MotionKit.setState(sbSendBtn, { hasExplicitWidth: true, width: initBtnWidth });
    sbTextSpan.textContent = sbShortText;
    sbCurrentFullText = sbShortText;
    sbStartWidthWatcher();
}

const ButtonAnimator = { init: sbInit, switchToLong: sbSwitchToLong, switchToShort: sbSwitchToShort };
