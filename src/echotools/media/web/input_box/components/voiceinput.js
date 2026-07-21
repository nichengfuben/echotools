// ========================= 录音按钮: 模拟语音转文字 =========================
const viVoiceBtn = document.getElementById("voiceBtn");
const viTextarea = document.getElementById("chatInput");
const viSendButton = document.getElementById("sendButton");
if (!viVoiceBtn || !viTextarea || !viSendButton) {
    // elements missing in embed mode
} else {
const viOriginalSvgHtml = viVoiceBtn.innerHTML;
const viVoiceWords = [
    "你好", "我在听", "语音识别", "模拟文本", "继续输入",
    "你好吗", "今天天气不错", "这是一段测试", "录音中",
    "请说", "消息内容", "实时转写", "语音助手"
];
let viIsRecording = false;
let viRecordingInterval = null;
let viGlobalKeydownHandler = null;
let viWordIndex = 0;

function viAppendVoiceText() {
    if (!viIsRecording) return;
    const word = viVoiceWords[viWordIndex % viVoiceWords.length];
    viWordIndex += 1;
    viTextarea.value = viTextarea.value + word;
    viTextarea.dispatchEvent(new Event("input", { bubbles: true }));
    viTextarea.scrollTop = viTextarea.scrollHeight;
}

function viStopRecording() {
    if (!viIsRecording) return;
    viIsRecording = false;
    if (viRecordingInterval) { clearInterval(viRecordingInterval); viRecordingInterval = null; }
    if (viGlobalKeydownHandler) {
        document.removeEventListener("keydown", viGlobalKeydownHandler);
        viGlobalKeydownHandler = null;
    }
    viVoiceBtn.innerHTML = viOriginalSvgHtml;
    viWordIndex = 0;
}

function viEnsureKeydownHandler() {
    if (viGlobalKeydownHandler) return;
    viGlobalKeydownHandler = function() {
        if (viIsRecording) viStopRecording();
    };
    document.addEventListener("keydown", viGlobalKeydownHandler);
}

function viStartRecording() {
    if (viIsRecording) return;
    if (viRecordingInterval) clearInterval(viRecordingInterval);
    viIsRecording = true;
    viWordIndex = 0;
    viVoiceBtn.innerHTML = "";
    viVoiceBtn.appendChild(createColoredGif());
    viRecordingInterval = setInterval(viAppendVoiceText, 400);
    viEnsureKeydownHandler();
}

function viOnVoiceClick(e) {
    e.stopPropagation();
    if (viIsRecording) viStopRecording();
    else viStartRecording();
}

function viOnTextareaClick() {
    if (viIsRecording) viStopRecording();
}

function viOnSendClick() {
    if (viIsRecording) viStopRecording();
}

viVoiceBtn.addEventListener("click", viOnVoiceClick);
viTextarea.addEventListener("click", viOnTextareaClick);
viSendButton.addEventListener("click", viOnSendClick);
}
