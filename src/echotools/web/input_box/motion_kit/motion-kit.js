// ========================= MotionKit =========================
const MotionKit = (() => {
    const stateMap = new WeakMap();
    const mouseState = { x: 0, y: 0, down: false };

    function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }

    function getState(element) {
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

    function applyState(element) {
        const state = getState(element);
        element.style.transform =
            `translate3d(${state.x}px, ${state.y}px, 0) scale(${state.size / 100}) rotate(${state.rotation}deg)`;
        element.style.opacity = String(clamp(state.opacity, 0, 1));
        const filters = [];
        if (state.color !== 0) filters.push(`hue-rotate(${state.color}deg)`);
        if (state.brightness !== 0) filters.push(`brightness(${100 + state.brightness}%)`);
        element.style.filter = filters.join(" ");
        if (state.hasExplicitWidth) element.style.width = `${Math.max(0, state.width)}px`;
        if (state.hasExplicitHeight) element.style.height = `${Math.max(0, state.height)}px`;
    }

    function getPointerHitElement() { return document.elementFromPoint(mouseState.x, mouseState.y); }

    function isPointerInside(element) {
        const rect = element.getBoundingClientRect();
        return mouseState.x >= rect.left && mouseState.x <= rect.right &&
               mouseState.y >= rect.top && mouseState.y <= rect.bottom;
    }

    function isPointerInsideExcluding(element, excludeSelector) {
        if (!isPointerInside(element)) return false;
        const hit = getPointerHitElement();
        if (!hit) return true;
        const excluded = hit.closest(excludeSelector);
        if (excluded && element.contains(excluded)) return false;
        return true;
    }

    function createLoop(step) {
        let running = true;
        function frame() { if (!running) return; step(); requestAnimationFrame(frame); }
        requestAnimationFrame(frame);
        return { stop() { running = false; } };
    }

    function animateState(element, update, done, finish) {
        return new Promise((resolve) => {
            function frame() {
                const state = getState(element);
                update(state);
                applyState(element);
                if (done(state)) { finish(state); applyState(element); resolve(); return; }
                requestAnimationFrame(frame);
            }
            requestAnimationFrame(frame);
        });
    }

    function setState(element, patch = {}) {
        const state = getState(element);
        Object.assign(state, patch);
        applyState(element);
        return state;
    }

    function sizeTo(element, target, rate = 8) {
        return animateState(element,
            (state) => { state.size += (target - state.size) / rate; },
            (state) => Math.abs(target - state.size) < 0.5,
            (state) => { state.size = target; });
    }

    function opacityTo(element, target, rate = 8) {
        return animateState(element,
            (state) => { state.opacity += (target - state.opacity) / rate; },
            (state) => Math.abs(target - state.opacity) < 0.01,
            (state) => { state.opacity = target; });
    }

    function widthTo(element, target, rate = 6) {
        const state = getState(element);
        state.hasExplicitWidth = true;
        return animateState(element,
            (state) => { state.width += (target - state.width) / rate; },
            (state) => Math.abs(target - state.width) < 1,
            (state) => { state.width = target; });
    }

    function floatScale(element, hover = 108, press = 96, normal = 100, damping = 0.18) {
        return createLoop(() => {
            const state = getState(element);
            const inside = isPointerInside(element);
            const target = mouseState.down && inside ? press : inside ? hover : normal;
            state.size += (target - state.size) * damping;
            applyState(element);
        });
    }

    function floatScaleConditional(element, resolver, damping = 0.18) {
        return createLoop(() => {
            const state = getState(element);
            const target = resolver({
                element, state, mouseState,
                hitElement: getPointerHitElement(),
                isInside: isPointerInside(element)
            });
            state.size += (target - state.size) * damping;
            applyState(element);
        });
    }

    window.addEventListener("pointermove", (event) => {
        mouseState.x = event.clientX; mouseState.y = event.clientY;
    }, { passive: true });
    window.addEventListener("pointerdown", () => { mouseState.down = true; }, { passive: true });
    window.addEventListener("pointerup", () => { mouseState.down = false; }, { passive: true });
    window.addEventListener("pointercancel", () => { mouseState.down = false; }, { passive: true });

    return {
        mouseState, clamp, getState, setState, applyState,
        getPointerHitElement, isPointerInside, isPointerInsideExcluding,
        createLoop, animateState, sizeTo, opacityTo, widthTo,
        floatScale, floatScaleConditional
    };
})();
