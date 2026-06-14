/**
 * InputBox — Portable chat input component.
 * Usage: InputBox.create(container, options)
 *
 * Options:
 *   placeholder: string
 *   maxRows / minRows: number
 *   limitThreshold: number (auto-convert to file if text exceeds)
 *   buttons: { file: bool, voice: bool, send: bool }
 *   voice: { sttModel, ttsModel, ttsPrompt }
 *   onSend: function(text, files)
 *   onVoiceStart / onVoiceEnd: function()
 */
(function() {
  'use strict';

  var _uid = 0;

  function InputBox(container, opts) {
    opts = opts || {};
    this._id = 'ib' + (++_uid);
    this._container = typeof container === 'string' ? document.querySelector(container) : container;
    this._opts = Object.assign({
      placeholder: 'Type a message...',
      maxRows: 6, minRows: 4,
      limitThreshold: 1024,
      buttons: { file: true, voice: true, send: true },
      voice: { sttModel: '', ttsModel: '', ttsPrompt: '' },
      onSend: null,
      onVoiceStart: null,
      onVoiceEnd: null,
    }, opts);
    this._files = [];
    this._isOverLimit = false;
    this._isRecording = false;
    this._mediaRecorder = null;
    this._audioChunks = [];
    this._render();
    this._bind();
  }

  InputBox.prototype._el = function(suffix) {
    return document.getElementById(this._id + '-' + suffix);
  };

  InputBox.prototype._render = function() {
    var id = this._id;
    var o = this._opts;
    var btns = o.buttons;
    var html = '<div class="ib-root" id="' + id + '-root">';
    // File zone
    html += '<div class="ib-file-zone" id="' + id + '-fileZone" style="display:none;"></div>';
    // Text area
    html += '<div class="ib-viewport" id="' + id + '-viewport" style="height:' + (o.minRows * 24) + 'px;">';
    html += '<textarea class="ib-textarea native-scroll-hidden" id="' + id + '-textarea" placeholder="' + o.placeholder + '" rows="' + o.minRows + '"></textarea>';
    html += '<div class="ib-caret" id="' + id + '-caret"></div>';
    html += '<div class="ib-scrollbar" id="' + id + '-scrollbar"><div class="ib-track"></div><div class="ib-thumb" id="' + id + '-thumb"></div></div>';
    html += '</div>';
    // Button bar
    html += '<div class="ib-bar">';
    html += '<div class="ib-bar-left">';
    if (btns.file) html += '<button class="ib-btn" id="' + id + '-fileBtn" title="Upload file"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z"/></svg></button>';
    if (btns.file) html += '<input type="file" id="' + id + '-fileInput" multiple style="display:none;">';
    if (btns.voice) html += '<button class="ib-btn" id="' + id + '-voiceBtn" title="Voice input"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"/></svg></button>';
    html += '</div>';
    html += '<div class="ib-bar-right">';
    html += '<span class="ib-file-count" id="' + id + '-fileCount" style="display:none;"></span>';
    if (btns.send) html += '<button class="ib-send" id="' + id + '-sendBtn"><span>Send</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 12L3.269 3.125A59.769 59.769 0 0121.485 12 59.768 59.768 0 013.27 20.875L5.999 12Zm0 0h7.5"/></svg></button>';
    html += '</div></div></div>';
    this._container.innerHTML = html;
  };

  InputBox.prototype._bind = function() {
    var self = this;
    var ta = this._el('textarea');
    var vp = this._el('viewport');
    var sendBtn = this._el('sendBtn');
    var fileBtn = this._el('fileBtn');
    var fileInput = this._el('fileInput');
    var voiceBtn = this._el('voiceBtn');
    var o = this._opts;

    // Auto-height
    ta.addEventListener('input', function() { self._syncHeight(); self._checkLimit(); });
    ta.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); self._doSend(); }
    });

    // Paste: long text -> file
    ta.addEventListener('paste', function(e) {
      e.preventDefault();
      var text = (e.clipboardData || window.clipboardData).getData('text');
      if (text.length > o.limitThreshold) {
        self._addFile({ name: 'pasted_text.txt', text: text });
      } else {
        var s = ta.selectionStart, end = ta.selectionEnd;
        ta.value = ta.value.slice(0, s) + text + ta.value.slice(end);
        ta.selectionStart = ta.selectionEnd = s + text.length;
        self._syncHeight();
      }
    });

    // Send
    if (sendBtn) sendBtn.addEventListener('click', function() { self._doSend(); });

    // File upload
    if (fileBtn && fileInput) {
      fileBtn.addEventListener('click', function() { fileInput.click(); });
      fileInput.addEventListener('change', function() {
        for (var i = 0; i < fileInput.files.length; i++) {
          self._addFile(fileInput.files[i]);
        }
        fileInput.value = '';
      });
    }

    // Voice
    if (voiceBtn) voiceBtn.addEventListener('click', function() { self._toggleVoice(); });

    window.addEventListener('resize', function() { self._syncHeight(true); });
    this._syncHeight(true);
  };

  InputBox.prototype._syncHeight = function(immediate) {
    var ta = this._el('textarea');
    var vp = this._el('viewport');
    if (!ta || !vp) return;
    var o = this._opts;
    var lh = parseFloat(getComputedStyle(ta).lineHeight) || 24;
    var minH = lh * o.minRows, maxH = lh * o.maxRows;
    ta.style.height = '0px';
    var h = Math.min(maxH, Math.max(minH, ta.scrollHeight));
    ta.style.height = h + 'px';
    vp.style.height = h + 'px';
  };

  InputBox.prototype._checkLimit = function() {
    var ta = this._el('textarea');
    if (!ta) return;
    this._isOverLimit = ta.value.length > this._opts.limitThreshold;
    var sendBtn = this._el('sendBtn');
    if (sendBtn) {
      var span = sendBtn.querySelector('span');
      if (span) span.textContent = this._isOverLimit ? 'Save as File' : 'Send';
    }
  };

  InputBox.prototype._doSend = function() {
    var ta = this._el('textarea');
    if (!ta) return;
    var text = ta.value.trim();
    if (this._isOverLimit && text) {
      this._addFile({ name: 'long_text.txt', text: text });
      ta.value = '';
      this._isOverLimit = false;
      this._checkLimit();
      this._syncHeight();
      return;
    }
    if (!text && this._files.length === 0) return;
    if (this._opts.onSend) this._opts.onSend(text, this._files.slice());
    ta.value = '';
    this._files = [];
    this._isOverLimit = false;
    this._checkLimit();
    this._syncHeight();
    this._renderFiles();
    ta.focus();
  };

  InputBox.prototype._addFile = function(fileOrText) {
    if (fileOrText.text) {
      this._files.push({ name: fileOrText.name, size: fileOrText.text.length, text: fileOrText.text });
    } else {
      this._files.push({ name: fileOrText.name, size: fileOrText.size, file: fileOrText });
    }
    this._renderFiles();
  };

  InputBox.prototype._renderFiles = function() {
    var zone = this._el('fileZone');
    var countEl = this._el('fileCount');
    if (!zone) return;
    if (this._files.length === 0) {
      zone.style.display = 'none';
      if (countEl) countEl.style.display = 'none';
      return;
    }
    zone.style.display = 'flex';
    var self = this;
    zone.innerHTML = this._files.map(function(f, i) {
      var sizeStr = f.size > 1024 ? (f.size / 1024).toFixed(1) + ' KB' : f.size + ' B';
      return '<div class="ib-file-card"><span class="ib-file-name">' + f.name + '</span><span class="ib-file-size">' + sizeStr + '</span><button class="ib-file-rm" data-idx="' + i + '">&times;</button></div>';
    }).join('');
    zone.querySelectorAll('.ib-file-rm').forEach(function(btn) {
      btn.addEventListener('click', function() {
        self._files.splice(parseInt(btn.dataset.idx), 1);
        self._renderFiles();
      });
    });
    if (countEl) { countEl.style.display = ''; countEl.textContent = this._files.length + ' file(s)'; }
  };

  InputBox.prototype._toggleVoice = function() {
    if (this._isRecording) { this._stopVoice(); } else { this._startVoice(); }
  };

  InputBox.prototype._startVoice = function() {
    var self = this;
    var voiceBtn = this._el('voiceBtn');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (voiceBtn) voiceBtn.title = 'Voice not supported';
      return;
    }
    this._isRecording = true;
    this._audioChunks = [];
    if (voiceBtn) voiceBtn.classList.add('ib-recording');
    if (this._opts.onVoiceStart) this._opts.onVoiceStart();

    navigator.mediaDevices.getUserMedia({ audio: true }).then(function(stream) {
      self._mediaRecorder = new MediaRecorder(stream);
      self._mediaRecorder.ondataavailable = function(e) { self._audioChunks.push(e.data); };
      self._mediaRecorder.onstop = function() {
        stream.getTracks().forEach(function(t) { t.stop(); });
        var blob = new Blob(self._audioChunks, { type: 'audio/webm' });
        self._processVoiceAudio(blob);
      };
      self._mediaRecorder.start();
    }).catch(function(err) {
      self._isRecording = false;
      if (voiceBtn) voiceBtn.classList.remove('ib-recording');
    });
  };

  InputBox.prototype._stopVoice = function() {
    this._isRecording = false;
    var voiceBtn = this._el('voiceBtn');
    if (voiceBtn) voiceBtn.classList.remove('ib-recording');
    if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
      this._mediaRecorder.stop();
    }
    if (this._opts.onVoiceEnd) this._opts.onVoiceEnd();
  };

  InputBox.prototype._processVoiceAudio = function(blob) {
    // Send to STT endpoint if configured
    var sttModel = this._opts.voice.sttModel;
    if (!sttModel) {
      // No STT model configured, just notify
      console.log('InputBox: No STT model configured, audio captured but not transcribed');
      return;
    }
    var self = this;
    var fd = new FormData();
    fd.append('file', blob, 'voice.webm');
    fd.append('model', sttModel);
    fetch('/v1/audio/transcriptions', { method: 'POST', body: fd })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.text) {
          var ta = self._el('textarea');
          if (ta) { ta.value += data.text; self._syncHeight(); }
        }
      })
      .catch(function(err) { console.error('InputBox STT error:', err); });
  };

  InputBox.prototype.getText = function() { return (this._el('textarea') || {}).value || ''; };
  InputBox.prototype.setText = function(v) { var ta = this._el('textarea'); if (ta) { ta.value = v; this._syncHeight(); } };
  InputBox.prototype.getFiles = function() { return this._files.slice(); };
  InputBox.prototype.focus = function() { var ta = this._el('textarea'); if (ta) ta.focus(); };

  // Factory
  InputBox.create = function(container, options) {
    return new InputBox(container, options);
  };

  window.InputBox = InputBox;
})();
