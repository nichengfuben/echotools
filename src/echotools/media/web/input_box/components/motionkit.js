/** MotionKit animation helpers (top-level functions, no IIFE). */

const stateMap = new WeakMap();
const mouseState = { x: 0, y: 0, down: false };

function mkClamp(value, min, max) { return Math.min(max, Math.max(min, value)); }

function mkGetState(element) {
    if (!stateMap.has(element)) {
        const rect = element.getBoundingClientRect();
        const computed = getComputedStyle(element);
        stateMap.set(element, {
            x: 0, y: 0, size: 100,
            width: rect.width, height: rect.height,
            opacity: Number.parseFloat(computed.opacity) || 1,
            color: 0, rotation: 0, brightness: 0,
            hasExplicitWidth: false, hasExplicitHeight: false
        });
    }
    return stateMap.get(element);
}

function mkApplyState(element) {
    const state = mkGetState(element);
    element.style.transform =
        `translate3d(${state.x}px, ${state.y}px, 0) scale(${state.size / 100}) rotate(${state.rotation}deg)`;
    element.style.opacity = String(mkClamp(state.opacity, 0, 1));
    const filters = [];
    if (state.color !== 0) filters.push(`hue-rotate(${state.color}deg)`);
    if (state.brightness !== 0) filters.push(`brightness(${100 + state.brightness}%)`);
    element.style.filter = filters.join(" ");
    if (state.hasExplicitWidth) element.style.width = `${Math.max(0, state.width)}px`;
    if (state.hasExplicitHeight) element.style.height = `${Math.max(0, state.height)}px`;
}

function mkGetPointerHitElement() { return document.elementFromPoint(mouseState.x, mouseState.y); }

function mkIsPointerInside(element) {
    const rect = element.getBoundingClientRect();
    return mouseState.x >= rect.left && mouseState.x <= rect.right &&
           mouseState.y >= rect.top && mouseState.y <= rect.bottom;
}

function mkIsPointerInsideExcluding(element, excludeSelector) {
    if (!mkIsPointerInside(element)) return false;
    const hit = mkGetPointerHitElement();
    if (!hit) return true;
    const excluded = hit.closest(excludeSelector);
    if (excluded && element.contains(excluded)) return false;
    return true;
}

function mkCreateLoop(step) {
    let running = true;
    function frame() { if (!running) return; step(); requestAnimationFrame(frame); }
    requestAnimationFrame(frame);
    return { stop() { running = false; } };
}

function mkAnimateFrame(element, update, done, finish, resolve) {
    const state = mkGetState(element);
    update(state);
    mkApplyState(element);
    if (done(state)) {
        finish(state);
        mkApplyState(element);
        resolve();
        return;
    }
    requestAnimationFrame(() => mkAnimateFrame(element, update, done, finish, resolve));
}

function mkAnimateState(element, update, done, finish) {
    return new Promise((resolve) => {
        requestAnimationFrame(() => mkAnimateFrame(element, update, done, finish, resolve));
    });
}

function mkSetState(element, patch) {
    const state = mkGetState(element);
    Object.assign(state, patch || {});
    mkApplyState(element);
    return state;
}

function mkSizeTo(element, target, rate) {
    rate = rate || 8;
    return mkAnimateState(element,
        (state) => { state.size += (target - state.size) / rate; },
        (state) => Math.abs(target - state.size) < 0.5,
        (state) => { state.size = target; });
}

function mkOpacityTo(element, target, rate) {
    rate = rate || 8;
    return mkAnimateState(element,
        (state) => { state.opacity += (target - state.opacity) / rate; },
        (state) => Math.abs(target - state.opacity) < 0.01,
        (state) => { state.opacity = target; });
}

function mkWidthTo(element, target, rate) {
    rate = rate || 6;
    const state = mkGetState(element);
    state.hasExplicitWidth = true;
    return mkAnimateState(element,
        (state) => { state.width += (target - state.width) / rate; },
        (state) => Math.abs(target - state.width) < 1,
        (state) => { state.width = target; });
}

function mkFloatScale(element, hover, press, normal, damping) {
    hover = hover || 108; press = press || 96; normal = normal || 100; damping = damping || 0.18;
    return mkCreateLoop(() => {
        const state = mkGetState(element);
        const inside = mkIsPointerInside(element);
        const target = mouseState.down && inside ? press : inside ? hover : normal;
        state.size += (target - state.size) * damping;
        mkApplyState(element);
    });
}

function mkFloatScaleConditional(element, resolver, damping) {
    damping = damping || 0.18;
    return mkCreateLoop(() => {
        const state = mkGetState(element);
        const target = resolver({
            element, state, mouseState,
            hitElement: mkGetPointerHitElement(),
            isInside: mkIsPointerInside(element)
        });
        state.size += (target - state.size) * damping;
        mkApplyState(element);
    });
}

function mkInitPointerListeners() {
    window.addEventListener("pointermove", (event) => {
        mouseState.x = event.clientX; mouseState.y = event.clientY;
    }, { passive: true });
    window.addEventListener("pointerdown", () => { mouseState.down = true; }, { passive: true });
    window.addEventListener("pointerup", () => { mouseState.down = false; }, { passive: true });
    window.addEventListener("pointercancel", () => { mouseState.down = false; }, { passive: true });
}

mkInitPointerListeners();

const MotionKit = {
    mouseState, clamp: mkClamp, getState: mkGetState, setState: mkSetState, applyState: mkApplyState,
    getPointerHitElement: mkGetPointerHitElement, isPointerInside: mkIsPointerInside,
    isPointerInsideExcluding: mkIsPointerInsideExcluding,
    createLoop: mkCreateLoop, animateState: mkAnimateState, sizeTo: mkSizeTo, opacityTo: mkOpacityTo,
    widthTo: mkWidthTo, floatScale: mkFloatScale, floatScaleConditional: mkFloatScaleConditional
};
