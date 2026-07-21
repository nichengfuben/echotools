// ========================= 应用状态 =========================
const AppState = { files: [], isTextOverLimit: false, limitThreshold: 1024 };

// ========================= 浮现 + hover 动效 =========================
function appearIn(element, delay = 0, rate = 5) {
    MotionKit.setState(element, { size: 0, opacity: 0 });
    return new Promise(resolve => {
        setTimeout(() => {
            Promise.all([MotionKit.sizeTo(element, 100, rate), MotionKit.opacityTo(element, 1, rate)]).then(resolve);
        }, delay);
    });
}

function initAllMotionEffects() {
    const inputSection = document.getElementById("mainInputSection");
    const toolBtns = document.querySelectorAll('.tool-btn');
    const sendBtn = document.getElementById("sendButton");

    appearIn(inputSection, 0, 5);
    toolBtns.forEach((btn, i) => appearIn(btn, 60 + i * 45, 5));
    appearIn(sendBtn, 60 + toolBtns.length * 45, 5);

    const clearBtn = document.getElementById("clearAllFilesBtn");
    MotionKit.setState(clearBtn, { size: 80, opacity: 0 });

    setTimeout(attachHoverMotion, 60 + toolBtns.length * 45 + 350);
}

function resolveInputHoverScale(ctx, element) {
    if (!ctx.isInside) return 100;
    const hitButton = ctx.hitElement ? ctx.hitElement.closest("button") : null;
    if (hitButton && element.contains(hitButton)) return 100;
    return ctx.mouseState.down ? 99 : 102;
}

function attachHoverMotion() {
    const toolButtons = Array.from(document.querySelectorAll('.tool-btn'));
    const sendBtn = document.getElementById('sendButton');
    const clearBtn = document.getElementById('clearAllFilesBtn');
    const inputContainer = document.getElementById('mainInputSection');

    toolButtons.forEach((btn) => MotionKit.floatScale(btn, 108, 96, 100, 0.18));
    if (sendBtn) MotionKit.floatScale(sendBtn, 107, 96, 100, 0.18);
    if (clearBtn) MotionKit.floatScale(clearBtn, 108, 96, 100, 0.18);

    if (inputContainer) {
        MotionKit.floatScaleConditional(
            inputContainer,
            (ctx) => resolveInputHoverScale(ctx, inputContainer),
            0.15
        );
    }
}

initAllMotionEffects();
ButtonAnimator.init();
